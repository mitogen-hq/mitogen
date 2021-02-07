# Copyright 2019, David Wilson
#
# Redistribution and use in source and binary forms, with or without
# modification, are permitted provided that the following conditions are met:
#
# 1. Redistributions of source code must retain the above copyright notice,
# this list of conditions and the following disclaimer.
#
# 2. Redistributions in binary form must reproduce the above copyright notice,
# this list of conditions and the following disclaimer in the documentation
# and/or other materials provided with the distribution.
#
# 3. Neither the name of the copyright holder nor the names of its contributors
# may be used to endorse or promote products derived from this software without
# specific prior written permission.
#
# THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS"
# AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE
# IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE
# ARE DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT HOLDER OR CONTRIBUTORS BE
# LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR
# CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF
# SUBSTITUTE GOODS OR SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS
# INTERRUPTION) HOWEVER CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN
# CONTRACT, STRICT LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE)
# ARISING IN ANY WAY OUT OF THE USE OF THIS SOFTWARE, EVEN IF ADVISED OF THE
# POSSIBILITY OF SUCH DAMAGE.

# !mitogen: minify_safe

"""
:mod:`mitogen.fakessh` is a stream implementation that starts a subprocess with
its environment modified such that ``PATH`` searches for `ssh` return a Mitogen
implementation of SSH. When invoked, this implementation arranges for the
command line supplied by the caller to be executed in a remote context, reusing
the parent context's (possibly proxied) connection to that remote context.

This allows tools like `rsync` and `scp` to transparently reuse the connections
and tunnels already established by the host program to connect to a target
machine, without wasteful redundant SSH connection setup, 3-way handshakes, or
firewall hopping configurations, and enables these tools to be used in
impossible scenarios, such as over `sudo` with ``requiretty`` enabled.

The fake `ssh` command source is written to a temporary file on disk, and
consists of a copy of the :py:mod:`mitogen.core` source code (just like any
other child context), with a line appended to cause it to connect back to the
host process over an FD it inherits. As there is no reliance on an existing
filesystem file, it is possible for child contexts to use fakessh.

As a consequence of connecting back through an inherited FD, only one SSH
invocation is possible, which is fine for tools like `rsync`, however in future
this restriction will be lifted.

Sequence:

    1. ``fakessh`` Context and Stream created by parent context. The stream's
       buffer has a :py:func:`_fakessh_main` :py:data:`CALL_FUNCTION
       <mitogen.core.CALL_FUNCTION>` enqueued.
    2. Target program (`rsync/scp/sftp`) invoked, which internally executes
       `ssh` from ``PATH``.
    3. :py:mod:`mitogen.core` bootstrap begins, recovers the stream FD
       inherited via the target program, established itself as the fakessh
       context.
    4. :py:func:`_fakessh_main` :py:data:`CALL_FUNCTION
       <mitogen.core.CALL_FUNCTION>` is read by fakessh context,

        a. sets up :py:class:`IoPump` for stdio, registers
           control_handle and stdin_handle for local context.
        b. Enqueues :py:data:`CALL_FUNCTION <mitogen.core.CALL_FUNCTION>` for
           :py:func:`_start_slave` invoked in target context,

            i. the program from the `ssh` command line is started
            ii. sets up :py:class:`IoPump` for `ssh` command line process's
                stdio pipes
            iii. returns `(control_handle, stdin_handle)` to
                 :py:func:`_fakessh_main`

    5. :py:func:`_fakessh_main` receives control/stdin handles from from
       :py:func:`_start_slave`,

        a. registers remote's control_handle and stdin_handle with local
           :py:class:`IoPump`.
        b. sends `("start", ())` to remote's control_handle to start receiving
           stdout from remote subprocess
        c. registers local :py:class:`IoPump` with
           :py:class:`mitogen.core.Broker` to start sending stdin to remote
           subprocess
        d. forwards _on_stdin data to stdout with IoPump.write and IoPump.close
        e. loops waiting for `("exit", status)` control message from slave
           and for pending writes to stdout to complete.

    6. :py:func:`_start_slave` control channel receives `("start", ())`,

        a. registers local :py:class:`IoPump` with
           :py:class:`mitogen.core.Broker` to start receiving and forwarding
           subprocess stdout
        b. forwards _on_stdin data to subprocess stdin with IoPump.write and
           IoPump.close
        c. shuts down and sends `("exit", status)` control message to master
           after reaching EOF from subprocess stdout

    "stdin" handle and handler naming is a little misleading because they are
    used to forard stdin data from the master to the slave, but stdout data from
    the slave to the master
"""

import getopt
import inspect
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import threading

import mitogen.core
import mitogen.master
import mitogen.parent

from mitogen.core import LOG, IOLOG


SSH_GETOPTS = (
    "1246ab:c:e:fgi:kl:m:no:p:qstvx"
    "ACD:E:F:I:KL:MNO:PQ:R:S:TVw:W:XYy"
)

_mitogen = None


class IoPump(mitogen.core.Protocol):
    """
    Raw data protocol that transmits and receives in two directions:

    - Forwarding data from protocol receive api to IoPump 'receive' and
      'disconnect' listeners
    - Forwarding data from IoPump.write() and IoPump.close() calls to protocol
      transmit api

    Overrides default protocol on_disconnect and on_shutdown methods, only
    closing the receive side when an on_disconnect EOF is reached, and only
    closing the transmit side when close() is called or on_shutdown termination
    is forced. This way when EOF is reached for receiving data, outgoing data is
    still transmitted in full without being truncated, and vice versa.

    Back pressure is implemented in the receive direction ('receive' listeners
    can block) but no back pressure exists in transmit direction (IoPump.write
    and IoPump.close calls never block), so writing data too fast can use an
    unbounded amount of memory.

    The lack of back pressure for writes should not normally be problem when
    IoPump is used by fakessh, because the data should be coming in from a slow
    remote source and being transmitted to a fast local process. But there could
    be cases where the local process is too slow (maybe writing to a slow disk)
    and memory usage gets out of hand. In this case some kind of blocking or
    rate limiting may need to be implemented for IoPump.write.
    """
    _output_buf = b''
    _closed = False

    def __init__(self, broker):
        self._broker = broker

    def write(self, s):
        self._output_buf += s
        self._broker._start_transmit(self.stream)

    def close(self):
        self._closed = True
        # If local process hasn't exitted yet, ensure its write buffer is
        # drained before lazily triggering disconnect in on_transmit.
        if not self.stream.transmit_side.closed:
            self._broker._start_transmit(self.stream)

    def on_shutdown(self, broker):
        self.close()
        super().on_shutdown(broker)

    def on_transmit(self, broker):
        written = self.stream.transmit_side.write(self._output_buf)
        IOLOG.debug('%r.on_transmit() -> len %r', self, written)
        self._output_buf = self._output_buf[written:]
        if not self._output_buf:
            broker._stop_transmit(self.stream)
            if self._closed:
                self.stream.transmit_side.close()
            mitogen.core.fire(self, 'write_done')

    def on_receive(self, broker, s):
        IOLOG.debug('%r.on_receive() -> len %r', self, len(s))
        mitogen.core.fire(self, 'receive', s)

    def on_disconnect(self, broker):
        broker.stop_receive(self.stream)
        self.stream.receive_side.close()
        mitogen.core.fire(self, 'disconnect')

    def __repr__(self):
        return 'IoPump(%r, %r)' % (
            self.stream.receive_side.fp.fileno(),
            self.stream.transmit_side.fp.fileno(),
        )


class Process(object):
    """
    Process manager responsible for forwarding data simultaneously in two
    directions:

    - From incoming self.stdin_handle data messages to file descriptor output
      via IoPump.write() and IoPump.close() calls
    - From input file descriptor IoPump 'receive' events to outgoing self.stdin
      data messages

    "stdin" naming is a little misleading because the stdin handle and handler
    are used to forward both stdin and stdout data, not just stdin data.
    """
    def __init__(self, router):
        self.router = router
        self.control_handle = router.add_handler(self._on_control)
        self.stdin_handle = router.add_handler(self._on_stdin)

    def start(self, dest, control_handle, stdin_handle, in_fd, out_fd, proc=None):
        self.control = mitogen.core.Sender(dest, control_handle)
        self.stdin = mitogen.core.Sender(dest, stdin_handle)
        self.pump = IoPump.build_stream(self.router.broker)
        mitogen.core.listen(self.pump.protocol, 'receive', self._on_pump_receive)
        mitogen.core.listen(self.pump.protocol, 'disconnect', self._on_pump_disconnect)
        mitogen.core.listen(self.pump.protocol, 'write_done', self._on_pump_write_done)
        self.pump.accept(in_fd, out_fd, cloexec=proc is not None)
        self.proc = proc
        if self.proc is None:
            self.exit_status = None
            self.wake_event = threading.Event()
            self.control.send(('start', ())) # start remote forwarding of process output
            self.router.broker.start_receive(self.pump) # start local forwarding of process input

    def __repr__(self):
        return 'Process(%r)' % (self.pump)

    def _on_proc_exit(self, status):
        LOG.debug('%r._on_proc_exit(%r)', self, status)
        self.control.send(('exit', status))

    def _on_stdin(self, msg):
        if msg.is_dead:
            IOLOG.debug('%r._on_stdin() -> %r', self, msg)
            self.pump.protocol.close()
            return

        data = msg.unpickle()
        IOLOG.debug('%r._on_stdin() -> len %d', self, len(data))
        self.pump.protocol.write(data)

    def _on_control(self, msg):
        if not msg.is_dead:
            command, arg = msg.unpickle(throw=False)
            LOG.debug('%r._on_control(%r, %s)', self, command, arg)

            if isinstance(command, bytes):
                command = command.decode()

            func = getattr(self, '_on_%s' % (command,), None)
            if func:
                return func(msg, arg)

            LOG.warning('%r: unknown command %r', self, command)

    def _on_start(self, msg, arg):
        # Triggered in fakessh slave process when fakessh master has sent
        # 'start' command and is ready to receive stdout data. Handle by calling
        # the broker to start receiving and forwarding stdout.
        assert self.proc is not None
        self.router.broker.start_receive(self.pump)

    def _on_exit(self, msg, arg):
        # Triggered in fakessh master process when fakessh slave has sent 'exit'
        # command with subprocess exit code. In this case pump.transit_side is
        # forwarding remote subprocess output to stdout. If the transmit side is
        # closed, all data has been written successfully and there's nothing
        # left to do except wake and exit. But if the transmit side is still
        # open, it means writes are still pending, and the fakessh master needs
        # to wait for _on_pump_write_done event before exiting.
        assert self.proc is None
        LOG.debug('on_exit: proc = %r', self.proc)
        self.exit_status = arg
        if self.pump.transmit_side.closed:
            self.wake_event.set()

    def _on_pump_receive(self, s):
        # Triggered in fakessh master process when stdin data is received and
        # needs to be forwarded, and in fakessh slave process when subprocess
        # stdout data is received and needs to be forwarded
        IOLOG.info('%r._on_pump_receive(len %d)', self, len(s))
        self.stdin.send(s)

    def _on_pump_disconnect(self):
        # Triggered in fakessh master process when stdin EOF is received, and in
        # fakessh slave process when subprocess stdout EOF is received. In the
        # slave case this is a signal to call waitpid and send the 'exit'
        # command and status code to the fakessh master
        LOG.debug('%r._on_pump_disconnect()', self)
        mitogen.core.fire(self, 'disconnect')
        self.stdin.close()
        if self.proc is not None:
            status = self.proc.wait()
            self._on_proc_exit(status)

    def _on_pump_write_done(self):
        # Triggered in fakessh master process when a write of subprocess output
        # data to stdout finishes, and in the fakessh slave process when a write
        # of input data to subprocess stdin finishes. This requires triggering
        # the wake event in the master process if waking was previously delayed
        # due to a pending write.
        LOG.debug('%r._on_write_done()', self)
        if self.proc is None and self.exit_status is not None:
            # Exit
            self.wake_event.set()

    def wait(self):
        # Called in fakessh master process to wait for wake event and subprocess
        # exit code
        assert self.proc is None
        while not self.wake_event.isSet():
            # Timeout is used so that sleep is interruptible, as blocking
            # variants of libc thread operations cannot be interrupted e.g. via
            # KeyboardInterrupt. isSet() test and wait() are separate since in
            # <2.7 wait() always returns None.
            self.wake_event.wait(0.1)


@mitogen.core.takes_router
def _start_slave(src_id, cmdline, control_handle, stdin_handle, router):
    """
    This runs in the target context, it is invoked by _fakessh_main running in
    the fakessh context immediately after startup. It starts the slave process
    (the the point where it has a stdin_handle to target but not stdout_chan to
    write to), and waits for main to.
    """
    LOG.debug('_start_slave(%r, %r)', router, cmdline)

    proc = subprocess.Popen(
        cmdline,
        # SSH server always uses user's shell.
        shell=True,
        # SSH server always executes new commands in the user's HOME.
        cwd=os.path.expanduser('~'),

        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
    )
    process = Process(router)
    dest = mitogen.core.Context(router, src_id)
    process.start(dest, control_handle, stdin_handle, proc.stdout, proc.stdin, proc=proc)
    return process.control_handle, process.stdin_handle


#
# SSH client interface.
#


def exit():
    _mitogen.broker.shutdown()


def die(msg, *args):
    if args:
        msg %= args
    sys.stderr.write('%s\n' % (msg,))
    exit()


def parse_args():
    hostname = None
    remain = sys.argv[1:]
    allopts = []
    restarted = 0

    while remain and restarted < 2:
        opts, args = getopt.getopt(remain, SSH_GETOPTS)
        remain = remain[:]  # getopt bug!
        allopts += opts
        if not args:
            break

        if not hostname:
            hostname = args.pop(0)
            remain = remain[remain.index(hostname) + 1:]

        restarted += 1

    return hostname, allopts, args


@mitogen.core.takes_econtext
def _fakessh_main(dest_context_id, econtext):
    hostname, opts, args = parse_args()
    if not hostname:
        die('Missing hostname')

    subsystem = False
    for opt, optarg in opts:
        if opt == '-s':
            subsystem = True
        else:
            LOG.debug('Warning option %s %s is ignored.', opt, optarg)

    LOG.debug('hostname: %r', hostname)
    LOG.debug('opts: %r', opts)
    LOG.debug('args: %r', args)

    if subsystem:
        die('-s <subsystem> is not yet supported')

    if not args:
        die('fakessh: login mode not supported and no command specified')

    dest = mitogen.parent.Context(econtext.router, dest_context_id)

    # Even though SSH receives an argument vector, it still cats the vector
    # together before sending to the server, the server just uses /bin/sh -c to
    # run the command. We must remain puke-for-puke compatible.
    process = Process(econtext.router)
    control_handle, stdin_handle = dest.call(_start_slave,
        mitogen.context_id, ' '.join(args),
        process.control_handle, process.stdin_handle)

    LOG.debug('_fakessh_main: received control_handle=%r, stdin_handle=%r',
              control_handle, stdin_handle)

    process.start(dest, control_handle, stdin_handle, os.fdopen(0, 'r+b', 0), os.fdopen(1, 'w+b', 0))
    process.wait()
    mitogen.exit_status = process.exit_status
    econtext.router.broker.shutdown()


def _get_econtext_config(context, sock2):
    parent_ids = mitogen.parent_ids[:]
    parent_ids.insert(0, mitogen.context_id)
    return {
        'context_id': context.context_id,
        'core_src_fd': None,
        'debug': getattr(context.router, 'debug', False),
        'in_fd': sock2.fileno(),
        'log_level': mitogen.parent.get_log_level(),
        'max_message_size': context.router.max_message_size,
        'out_fd': sock2.fileno(),
        'parent_ids': parent_ids,
        'profiling': getattr(context.router, 'profiling', False),
        'unidirectional': getattr(context.router, 'unidirectional', False),
        'setup_stdio': False,
        'send_ec2': False,
        'version': mitogen.__version__,
    }


#
# Public API.
#

@mitogen.core.takes_econtext
@mitogen.core.takes_router
def run(dest, router, args, deadline=None, econtext=None):
    """
    Run the command specified by `args` such that ``PATH`` searches for SSH by
    the command will cause its attempt to use SSH to execute a remote program
    to be redirected to use mitogen to execute that program using the context
    `dest` instead.

    :param list args:
        Argument vector.
    :param mitogen.core.Context dest:
        The destination context to execute the SSH command line in.

    :param mitogen.core.Router router:

    :param list[str] args:
        Command line arguments for local program, e.g.
        ``['rsync', '/tmp', 'remote:/tmp']``

    :returns:
        Exit status of the child process.
    """
    if econtext is not None:
        mitogen.parent.upgrade_router(econtext)

    context_id = router.allocate_id()
    fakessh = mitogen.parent.Context(router, context_id)
    fakessh.name = u'fakessh.%d' % (context_id,)

    sock1, sock2 = socket.socketpair()
    sock1.set_inheritable(True)
    sock2.set_inheritable(True)

    stream = mitogen.core.MitogenProtocol.build_stream(router, context_id, mitogen.context_id)
    stream.name = u'fakessh'
    stream.accept(sock1, sock1)
    router.register(fakessh, stream)
    router.route_monitor.notice_stream(stream)

    # Held in socket buffer until process is booted.
    fakessh.call_async(_fakessh_main, dest.context_id)

    tmp_path = tempfile.mkdtemp(prefix='mitogen_fakessh')
    try:
        ssh_path = os.path.join(tmp_path, 'ssh')
        fp = open(ssh_path, 'w')
        try:
            fp.write('#!%s\n' % (mitogen.parent.get_sys_executable(),))
            fp.write(inspect.getsource(mitogen.core))
            fp.write('\n')
            fp.write('ExternalContext(%r).main()\n' % (
                _get_econtext_config(fakessh, sock2),
            ))
            fp.write('sys.exit(mitogen.exit_status)\n')
        finally:
            fp.close()

        os.chmod(ssh_path, int('0755', 8))
        env = os.environ.copy()
        env.update({
            'PATH': '%s:%s' % (tmp_path, env.get('PATH', '')),
            'ARGV0': mitogen.parent.get_sys_executable(),
            'SSH_PATH': ssh_path,
        })

        proc = subprocess.Popen(args, env=env, close_fds=False)
        return proc.wait()
    finally:
        shutil.rmtree(tmp_path)
