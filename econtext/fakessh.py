"""
fakessh is a stream implementation that starts a local subprocess, substituting
one of the user-supplied arguments with the name of a "fake SSH command". When
invoked, this command passes its arguments back into the host context, and
begins tunnelling stdio from the child back to the configured target host.

This allows tools like rsync and scp to be invoked as subprocesses and reuse
the connections and tunnels already established by the host program to connect
to a target machine, without wasteful redundant SSH connection setup, 3-way
handshakes, or firewall hopping configurations.

The fake SSH command source is written to a temporary file on disk, and
consists of a copy of the econtext.core source code (just like any other child
context), with a line appended to cause it to connect back to the host process
over an FD it inherits.

As a consequence of connecting back through an inherited FD, only one SSH
invocation is possible, which is fine for tools like rsync.


Start sequence:

    1. fakessh invoked, captures command line.
    2. _fakessh_main invoked by parent,
        a. sets up IoPump for stdio, registers stdin_handle for local context
        b. _start_slave_process invoked in target context, passing stdin_handle
    3. _start_slave_process invoked in target context,
        a. the program from the SSH command line is invoked
        b. sets up IoPump for command line's pipes
        c. returns (control_handle, stdin_handle) to fakessh_main
    4. _fakessh_main receives (control_handle, stdin_handle),
        a. registers remote's stdin_handle with local IoPump
        b. sends ("start", local_stdin_handle) to control_handle
        c. registers local IoPump with broker
        d. loops waiting for 'local stdout closed && remote stdout closed'
    5. _start_slave_process control channel receives ("start", stdin_handle),
        a. registers remote's stdin_handle with local IoPump
        b. registers local IoPump with broker
        c. loops waiting for 'local stdout closed && remote stdout closed'

"""

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

import econtext.core
import econtext.master

from econtext.core import LOG, IOLOG


SSH_GETOPTS = (
    "1246ab:c:e:fgi:kl:m:no:p:qstvx"
    "ACD:E:F:I:KL:MNO:PQ:R:S:TVw:W:XYy"
)

_econtext = None


class IoPump(econtext.core.BasicStream):
    _output_buf = ''

    def __init__(self, process, broker, stdin_fd, stdout_fd):
        self.process = process
        self._broker = broker
        self.transmit_side = econtext.core.Side(self, stdin_fd)
        self.receive_side = econtext.core.Side(self, stdout_fd)

    def write(self, s):
        self._output_buf += s
        self._broker.start_transmit(self)

    def on_transmit(self, broker):
        written = self.transmit_side.write(self._output_buf)
        IOLOG.debug('%r.on_transmit() -> len %r', self, written)
        if written is None:
            self.on_disconnect(broker)
        else:
            self._output_buf = self._output_buf[written:]

        if not self._output_buf:
            broker.stop_transmit(self)

    def on_receive(self, broker):
        s = self.receive_side.read()
        IOLOG.debug('%r.on_receive() -> len %r', self, len(s))
        if not s:
            self.on_disconnect(broker)
        else:
            self.process.stdin.put(s)

    def on_disconnect(self, broker):
        super(IoPump, self).on_disconnect(broker)
        self.process.stdin.close()

    def __repr__(self):
        return 'IoPump(%r)' % (
            self.process,
        )


class Process(object):
    """
    Manages the lifetime and pipe connections of the SSH command running in the
    slave.
    """
    def __init__(self, router, stdin_fd, stdout_fd, pid=None):
        self.router = router
        self.stdin_fd = stdin_fd
        self.stdout_fd = stdout_fd
        self.pid = None
        self.control_handle = router.add_handler(self._on_control)
        self.stdin_handle = router.add_handler(self._on_stdin)
        self.pump = IoPump(self, router.broker, stdin_fd, stdout_fd)
        self.stdin = None
        self.control = None

    def __repr__(self):
        return 'Process(%r, %r, %r)' % (
            self.stdin_fd,
            self.stdout_fd,
            self.pid,
        )

    def _on_stdin(self, msg):
        if msg == econtext.core._DEAD:
            return

        data = msg.unpickle()
        IOLOG.debug('%r._on_stdin(%r)', self, data)

        if data == econtext.core._DEAD:
            self.pump.transmit_side.close()
        else:
            self.pump.write(data)

    def _on_control(self, msg):
        if msg == econtext.core._DEAD:
            return

        command, arg = msg.unpickle()
        LOG.debug('%r._on_control(%r, %s)', self, command, arg)

        if command == 'start':
            dest = econtext.core.Context(self.router, msg.src_id)
            self.control = econtext.core.Sender(dest, arg[0])
            self.stdin = econtext.core.Sender(dest, arg[1])
            self.router.broker.start_receive(self.pump)
        elif command == 'kill':
            if self.pid is not None:
                os.kill(self.pid, signal.SIGTERM)
        else:
            LOG.warning('%r: unknown command %r', self, command)

    def start_master(self, stdin, control):
        self.stdin = stdin
        self.control = control
        control.put(('start', (self.control_handle, self.stdin_handle)))
        self.router.broker.start_receive(self.pump)

    def wait(self):
        import time
        time.sleep(3)

def _start_slave_process(econtext_, src_id, args):
    """
    This runs in the target context, it is invoked by _fakessh_main running in
    the fakessh context immediately after startup. It starts the slave process
    (the the point where it has a stdin_handle to target but not stdout_chan to
    write to), and waits for main to 
    """
    LOG.debug('_start_slave_process(%r, %r)', econtext_, args)

    proc = subprocess.Popen(args,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
    )

    process = Process(econtext_.router,
        proc.stdin.fileno(),
        proc.stdout.fileno(),
        proc.pid,
    )
    return process.control_handle, process.stdin_handle


#
# SSH client interface.
#


def exit():
    _econtext.broker.shutdown()


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


def _fakessh_main(econtext_, dest_context_id):
    hostname, opts, args = parse_args()
    if not hostname:
        die('Missing hostname')

    for opt, optarg in opts:
        if 0 and opt == '-s':
            subsystem = True
        else:
            LOG.debug('Warning option %s %s is ignored.', opt, optarg)

    LOG.info('hostname: %r', hostname)
    LOG.info('opts: %r', opts)
    LOG.info('args: %r', args)

    dest = econtext.master.Context(econtext_.router, dest_context_id)
    control_handle, stdin_handle = dest.call_with_deadline(None, True,
        _start_slave_process, econtext.context_id, args)

    LOG.debug('_fakessh_main: received control_handle=%r, stdin_handle=%r',
              control_handle, stdin_handle)

    process = Process(econtext_.router, 1, 0)
    process.start_master(
        stdin=econtext.core.Sender(dest, stdin_handle),
        control=econtext.core.Sender(dest, control_handle),
    )
    process.wait()
    process.control.put(('kill', None))


#
# Public API.
#

def run_with_fake_ssh(dest, router, args, deadline=None):
    context_id = router.context_id_counter.next()
    fakessh = econtext.master.Context(router, context_id)
    fakessh.name = 'fakessh'

    sock1, sock2 = socket.socketpair()
    econtext.core.set_cloexec(sock1.fileno())

    stream = econtext.core.Stream(router, context_id, fakessh.key)
    stream.accept(sock1.fileno(), sock1.fileno())
    router.register(fakessh, stream)

    # Held in socket buffer until process is booted.
    fakessh.call_async(True, _fakessh_main, dest.context_id)

    tmp_path = tempfile.mkdtemp(prefix='econtext_fakessh')
    try:
        ssh_path = os.path.join(tmp_path, 'ssh')
        fp = file(ssh_path, 'w')
        try:
            fp.write('#!/usr/bin/env python\n')
            fp.write(inspect.getsource(econtext.core))
            fp.write('\n')
            fp.write('ExternalContext().main%r\n' % ((
                econtext.context_id,            # parent_id
                context_id,                     # context_id
                fakessh.key,                    # key
                router.debug,                   # debug
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
            'ARGV0': `[sys.executable]`,
            'SSH_PATH': ssh_path,
        })

        proc = subprocess.Popen(args, env=env)
        proc.wait()
    finally:
        shutil.rmtree(tmp_path)
