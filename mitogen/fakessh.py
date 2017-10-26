import getopt
import inspect
import logging
import os
import shutil
import signal
import socket
import subprocess
import sys
import tempfile
import threading

import mitogen.core
import mitogen.master

from mitogen.core import LOG, IOLOG


SSH_GETOPTS = (
    "1246ab:c:e:fgi:kl:m:no:p:qstvx"
    "ACD:E:F:I:KL:MNO:PQ:R:S:TVw:W:XYy"
)

_mitogen = None


class IoPump(mitogen.core.BasicStream):
    _output_buf = ''
    _closed = False

    def __init__(self, broker, stdin_fd, stdout_fd):
        self._broker = broker
        self.receive_side = mitogen.core.Side(self, stdout_fd)
        self.transmit_side = mitogen.core.Side(self, stdin_fd)

    def write(self, s):
        self._output_buf += s
        self._broker.start_transmit(self)

    def close(self):
        self._closed = True
        # If local process hasn't exitted yet, ensure its write buffer is
        # drained before lazily triggering disconnect in on_transmit.
        if self.transmit_side.fd is not None:
            self._broker.start_transmit(self)

    def on_shutdown(self, broker):
        self.close()

    def on_transmit(self, broker):
        written = self.transmit_side.write(self._output_buf)
        IOLOG.debug('%r.on_transmit() -> len %r', self, written)
        if written is None:
            self.on_disconnect(broker)
        else:
            self._output_buf = self._output_buf[written:]

        if not self._output_buf:
            broker.stop_transmit(self)
            if self._closed:
                self.on_disconnect(broker)

    def on_receive(self, broker):
        s = self.receive_side.read()
        IOLOG.debug('%r.on_receive() -> len %r', self, len(s))
        if s:
            mitogen.core.fire(self, 'receive', s)
        else:
            self.on_disconnect(broker)

    def __repr__(self):
        return 'IoPump(%r, %r)' % (
            self.receive_side.fd,
            self.transmit_side.fd,
        )


class Process(object):
    """
    Manages the lifetime and pipe connections of the SSH command running in the
    slave.
    """
    def __init__(self, router, stdin_fd, stdout_fd, proc=None):
        self.router = router
        self.stdin_fd = stdin_fd
        self.stdout_fd = stdout_fd
        self.proc = proc
        self.control_handle = router.add_handler(self._on_control)
        self.stdin_handle = router.add_handler(self._on_stdin)
        self.pump = IoPump(router.broker, stdin_fd, stdout_fd)
        self.stdin = None
        self.control = None
        self.wake_event = threading.Event()

        mitogen.core.listen(self.pump, 'disconnect', self._on_pump_disconnect)
        mitogen.core.listen(self.pump, 'receive', self._on_pump_receive)

        if proc:
            pmon = mitogen.master.ProcessMonitor.instance()
            pmon.add(proc.pid, self._on_proc_exit)

    def __repr__(self):
        return 'Process(%r, %r)' % (self.stdin_fd, self.stdout_fd)

    def _on_proc_exit(self, status):
        LOG.debug('%r._on_proc_exit(%r)', self, status)
        self.control.put(('exit', status))

    def _on_stdin(self, msg):
        if msg == mitogen.core._DEAD:
            return

        data = msg.unpickle()
        if data == mitogen.core._DEAD:
            IOLOG.debug('%r._on_stdin() -> %r', self, data)
            self.pump.close()
            return

        IOLOG.debug('%r._on_stdin() -> len %d', self, len(data))
        self.pump.write(data)

    def _on_control(self, msg):
        if msg != mitogen.core._DEAD:
            command, arg = msg.unpickle()
            LOG.debug('%r._on_control(%r, %s)', self, command, arg)

            func = getattr(self, '_on_%s' % (command,), None)
            if func:
                return func(msg, arg)

            LOG.warning('%r: unknown command %r', self, command)

    def _on_start(self, msg, arg):
        dest = mitogen.core.Context(self.router, msg.src_id)
        self.control = mitogen.core.Sender(dest, arg[0])
        self.stdin = mitogen.core.Sender(dest, arg[1])
        self.router.broker.start_receive(self.pump)

    def _on_exit(self, msg, arg):
        LOG.debug('on_exit: proc = %r', self.proc)
        if self.proc:
            self.proc.terminate()
        else:
            self.router.broker.shutdown()

    def _on_pump_receive(self, s):
        IOLOG.info('%r._on_pump_receive(len %d)', self, len(s))
        self.stdin.put(s)

    def _on_pump_disconnect(self):
        LOG.debug('%r._on_pump_disconnect()', self)
        mitogen.core.fire(self, 'disconnect')
        self.stdin.close()
        self.wake_event.set()

    def start_master(self, stdin, control):
        self.stdin = stdin
        self.control = control
        control.put(('start', (self.control_handle, self.stdin_handle)))
        self.router.broker.start_receive(self.pump)

    def wait(self):
        while not self.wake_event.isSet():
            # Timeout is used so that sleep is interruptible, as blocking
            # variants of libc thread operations cannot be interrupted e.g. via
            # KeyboardInterrupt. isSet() test and wait() are separate since in
            # <2.7 wait() always returns None.
            self.wake_event.wait(0.1)


@mitogen.core.takes_router
def _start_slave(src_id, cmdline, router):
    """
    This runs in the target context, it is invoked by _fakessh_main running in
    the fakessh context immediately after startup. It starts the slave process
    (the the point where it has a stdin_handle to target but not stdout_chan to
    write to), and waits for main to.
    """
    LOG.debug('_start_slave(%r, %r)', router, cmdline)

    proc = subprocess.Popen(cmdline,
        # SSH server always uses user's shell.
        shell=True,
        # SSH server always executes new commands in the user's HOME.
        cwd=os.path.expanduser('~'),

        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
    )

    process = Process(router,
        proc.stdin.fileno(),
        proc.stdout.fileno(),
        proc,
    )

    return process.control_handle, process.stdin_handle


#
# SSH client interface.
#


def exit():
    _mitogen.broker.shutdown()


def die(msg, *args):
    if args:
        msg %= args
    print msg
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

    dest = mitogen.master.Context(econtext.router, dest_context_id)

    # Even though SSH receives an argument vector, it still cats the vector
    # together before sending to the server, the server just uses /bin/sh -c to
    # run the command. We must remain puke-for-puke compatible.
    control_handle, stdin_handle = dest.call(_start_slave,
        mitogen.context_id, ' '.join(args))

    LOG.debug('_fakessh_main: received control_handle=%r, stdin_handle=%r',
              control_handle, stdin_handle)

    process = Process(econtext.router, 1, 0)
    process.start_master(
        stdin=mitogen.core.Sender(dest, stdin_handle),
        control=mitogen.core.Sender(dest, control_handle),
    )
    process.wait()
    process.control.put(('exit', None))


#
# Public API.
#

@mitogen.core.takes_econtext
@mitogen.core.takes_router
def run(dest, router, args, deadline=None, econtext=None):
    if econtext is not None:
        mitogen.master.upgrade_router(econtext)

    context_id = router.allocate_id()
    fakessh = mitogen.master.Context(router, context_id)
    fakessh.name = 'fakessh.%d' % (context_id,)

    sock1, sock2 = socket.socketpair()
    mitogen.core.set_cloexec(sock1.fileno())

    stream = mitogen.core.Stream(router, context_id)
    stream.name = 'fakessh'
    stream.accept(sock1.fileno(), sock1.fileno())
    router.register(fakessh, stream)

    # Held in socket buffer until process is booted.
    fakessh.call_async(_fakessh_main, dest.context_id)

    parent_ids = mitogen.parent_ids[:]
    parent_ids.insert(0, mitogen.context_id)

    tmp_path = tempfile.mkdtemp(prefix='mitogen_fakessh')
    try:
        ssh_path = os.path.join(tmp_path, 'ssh')
        fp = file(ssh_path, 'w')
        try:
            fp.write('#!%s\n' % (sys.executable,))
            fp.write(inspect.getsource(mitogen.core))
            fp.write('\n')
            fp.write('ExternalContext().main%r\n' % ((
                parent_ids,                     # parent_ids
                context_id,                     # context_id
                router.debug,                   # debug
                router.profiling,               # profiling
                logging.getLogger().level,      # log_level
                sock2.fileno(),                 # in_fd
                sock2.fileno(),                 # out_fd
                None,                           # core_src_fd
                False,                          # setup_stdio
            ),))
        finally:
            fp.close()

        os.chmod(ssh_path, 0755)
        env = os.environ.copy()
        env.update({
            'PATH': '%s:%s' % (tmp_path, env.get('PATH', '')),
            'ARGV0': sys.executable,
            'SSH_PATH': ssh_path,
        })

        proc = subprocess.Popen(args, env=env)
        return proc.wait()
    finally:
        shutil.rmtree(tmp_path)
