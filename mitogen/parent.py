# Copyright 2017, David Wilson
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

import getpass
import inspect
import logging
import os
import re
import select
import signal
import socket
import sys
import termios
import textwrap
import time
import zlib

import mitogen.core
from mitogen.core import LOG
from mitogen.core import IOLOG


DOCSTRING_RE = re.compile(r'""".+?"""', re.M | re.S)
COMMENT_RE = re.compile(r'^[ ]*#[^\n]*$', re.M)


class Argv(object):
    def __init__(self, argv):
        self.argv = argv

    def escape(self, x):
        s = '"'
        for c in x:
            if c in '\\$"`':
                s += '\\'
            s += c
        s += '"'
        return s

    def __str__(self):
        return ' '.join(map(self.escape, self.argv))


def get_log_level():
    return (LOG.level or logging.getLogger().level or logging.INFO)


def minimize_source(source):
    subber = lambda match: '""' + ('\n' * match.group(0).count('\n'))
    source = DOCSTRING_RE.sub(subber, source)
    source = COMMENT_RE.sub('', source)
    return source.replace('    ', '\t')


def flags(names):
    """Return the result of ORing a set of (space separated) :py:mod:`termios`
    module constants together."""
    return sum(getattr(termios, name) for name in names.split())


def cfmakeraw(tflags):
    """Given a list returned by :py:func:`termios.tcgetattr`, return a list
    that has been modified in the same manner as the `cfmakeraw()` C library
    function."""
    iflag, oflag, cflag, lflag, ispeed, ospeed, cc = tflags
    iflag &= ~flags('IGNBRK BRKINT PARMRK ISTRIP INLCR IGNCR ICRNL IXON')
    oflag &= ~flags('OPOST IXOFF')
    lflag &= ~flags('ECHO ECHOE ECHONL ICANON ISIG IEXTEN')
    cflag &= ~flags('CSIZE PARENB')
    cflag |= flags('CS8')

    # TODO: one or more of the above bit twiddles sets or omits a necessary
    # flag. Forcing these fields to zero, as shown below, gets us what we want
    # on Linux/OS X, but it is possibly broken on some other OS.
    iflag = 0
    oflag = 0
    lflag = 0
    return [iflag, oflag, cflag, lflag, ispeed, ospeed, cc]


def disable_echo(fd):
    old = termios.tcgetattr(fd)
    new = cfmakeraw(old)
    flags = (
        termios.TCSAFLUSH |
        getattr(termios, 'TCSASOFT', 0)
    )
    termios.tcsetattr(fd, flags, new)


def close_nonstandard_fds():
    for fd in xrange(3, 1024):
        try:
            os.close(fd)
        except OSError:
            pass


def create_child(*args):
    parentfp, childfp = socket.socketpair()
    pid = os.fork()
    if not pid:
        mitogen.core.set_block(childfp.fileno())
        os.dup2(childfp.fileno(), 0)
        os.dup2(childfp.fileno(), 1)
        childfp.close()
        parentfp.close()
        os.execvp(args[0], args)

    childfp.close()
    # Decouple the socket from the lifetime of the Python socket object.
    fd = os.dup(parentfp.fileno())
    parentfp.close()

    LOG.debug('create_child() child %d fd %d, parent %d, cmd: %s',
              pid, fd, os.getpid(), Argv(args))
    return pid, fd


def tty_create_child(*args):
    master_fd, slave_fd = os.openpty()
    disable_echo(master_fd)
    disable_echo(slave_fd)

    pid = os.fork()
    if not pid:
        mitogen.core.set_block(slave_fd)
        os.dup2(slave_fd, 0)
        os.dup2(slave_fd, 1)
        os.dup2(slave_fd, 2)
        close_nonstandard_fds()
        os.setsid()
        os.close(os.open(os.ttyname(1), os.O_RDWR))
        os.execvp(args[0], args)

    os.close(slave_fd)
    LOG.debug('tty_create_child() child %d fd %d, parent %d, cmd: %s',
              pid, master_fd, os.getpid(), Argv(args))
    return pid, master_fd


def write_all(fd, s, deadline=None):
    timeout = None
    written = 0

    while written < len(s):
        if deadline is not None:
            timeout = max(0, deadline - time.time())
        if timeout == 0:
            raise mitogen.core.TimeoutError('write timed out')

        _, wfds, _ = select.select([], [fd], [], timeout)
        if not wfds:
            continue

        n, disconnected = mitogen.core.io_op(os.write, fd, buffer(s, written))
        if disconnected:
            raise mitogen.core.StreamError('EOF on stream during write')

        written += n


def iter_read(fd, deadline=None):
    bits = []
    timeout = None

    while True:
        if deadline is not None:
            timeout = max(0, deadline - time.time())
            if timeout == 0:
                break

        rfds, _, _ = select.select([fd], [], [], timeout)
        if not rfds:
            continue

        s, disconnected = mitogen.core.io_op(os.read, fd, 4096)
        IOLOG.debug('iter_read(%r) -> %r', fd, s)
        if disconnected or not s:
            raise mitogen.core.StreamError(
                'EOF on stream; last 300 bytes received: %r' %
                (''.join(bits)[-300:],)
            )

        bits.append(s)
        yield s

    raise mitogen.core.TimeoutError('read timed out')


def discard_until(fd, s, deadline):
    for buf in iter_read(fd, deadline):
        if IOLOG.level == logging.DEBUG:
            for line in buf.splitlines():
                IOLOG.debug('discard_until: discarding %r', line)
        if buf.endswith(s):
            return


def upgrade_router(econtext):
    if not isinstance(econtext.router, Router):  # TODO
        econtext.router.__class__ = Router  # TODO
        econtext.router.id_allocator = ChildIdAllocator(econtext.router)
        LOG.debug('_proxy_connect(): constructing ModuleForwarder')
        ModuleForwarder(econtext.router, econtext.parent, econtext.importer)


def _docker_method():
    import mitogen.docker
    return mitogen.docker.Stream

def _local_method():
    return mitogen.parent.Stream

def _ssh_method():
    import mitogen.ssh
    return mitogen.ssh.Stream

def _sudo_method():
    import mitogen.sudo
    return mitogen.sudo.Stream


METHOD_NAMES = {
    'docker': _docker_method,
    'local': _local_method,
    'ssh': _ssh_method,
    'sudo': _sudo_method,
}


@mitogen.core.takes_econtext
def _proxy_connect(name, context_id, method_name, kwargs, econtext):
    mitogen.parent.upgrade_router(econtext)
    context = econtext.router._connect(
        context_id,
        METHOD_NAMES[method_name](),
        name=name,
        **kwargs
    )
    return context.name


class Stream(mitogen.core.Stream):
    """
    Base for streams capable of starting new slaves.
    """
    #: The path to the remote Python interpreter.
    python_path = 'python2.7'

    #: Maximum time to wait for a connection attempt.
    connect_timeout = 30.0

    #: Derived from :py:attr:`connect_timeout`; absolute floating point
    #: UNIX timestamp after which the connection attempt should be abandoned.
    connect_deadline = None

    #: True to cause context to write verbose /tmp/mitogen.<pid>.log.
    debug = False

    #: True to cause context to write /tmp/mitogen.stats.<pid>.<thread>.log.
    profiling = False

    def __init__(self, *args, **kwargs):
        super(Stream, self).__init__(*args, **kwargs)
        self.sent_modules = set(['mitogen', 'mitogen.core'])

    def construct(self, remote_name=None, python_path=None, debug=False,
                  connect_timeout=None, profiling=False, **kwargs):
        """Get the named context running on the local machine, creating it if
        it does not exist."""
        super(Stream, self).construct(**kwargs)
        if python_path:
            self.python_path = python_path
        if sys.platform == 'darwin' and self.python_path == '/usr/bin/python':
            # OS X installs a craptacular argv0-introspecting Python version
            # switcher as /usr/bin/python. Override attempts to call it with an
            # explicit call to python2.7
            self.python_path = '/usr/bin/python2.7'
        if connect_timeout:
            self.connect_timeout = connect_timeout
        if remote_name is None:
            remote_name = '%s@%s:%d'
            remote_name %= (getpass.getuser(), socket.gethostname(), os.getpid())
        self.remote_name = remote_name
        self.debug = debug
        self.profiling = profiling
        self.connect_deadline = time.time() + self.connect_timeout

    def on_shutdown(self, broker):
        """Request the slave gracefully shut itself down."""
        LOG.debug('%r closing CALL_FUNCTION channel', self)
        self.send(
            mitogen.core.Message(
                src_id=mitogen.context_id,
                dst_id=self.remote_id,
                handle=mitogen.core.SHUTDOWN,
            )
        )

    # Minimised, gzipped, base64'd and passed to 'python -c'. It forks, dups
    # file descriptor 0 as 100, creates a pipe, then execs a new interpreter
    # with a custom argv.
    # 'CONTEXT_NAME', 'PREAMBLE_COMPRESSED_LEN', and 'PREAMBLE_LEN' are
    # substituted with their respective values.
    # Optimized for minimum byte count after minification & compression.
    @staticmethod
    def _first_stage():
        R,W=os.pipe()
        r,w=os.pipe()
        if os.fork():
            os.dup2(0,100)
            os.dup2(R,0)
            os.dup2(r,101)
            os.close(R)
            os.close(r)
            os.close(W)
            os.close(w)
            os.environ['ARGV0']=sys.executable
            os.execl(sys.executable,'mitogen:CONTEXT_NAME')
        os.write(1,'EC0\n')
        C=_(os.fdopen(0,'rb').read(PREAMBLE_COMPRESSED_LEN),'zip')
        os.fdopen(W,'w',0).write(C)
        os.fdopen(w,'w',0).write('PREAMBLE_LEN\n'+C)
        os.write(1,'EC1\n')

    def get_boot_command(self):
        source = inspect.getsource(self._first_stage)
        source = textwrap.dedent('\n'.join(source.strip().split('\n')[2:]))
        source = source.replace('    ', '\t')
        source = source.replace('CONTEXT_NAME', self.remote_name)
        preamble_compressed = self.get_preamble()
        source = source.replace('PREAMBLE_COMPRESSED_LEN', str(len(preamble_compressed)))
        source = source.replace('PREAMBLE_LEN', str(len(zlib.decompress(preamble_compressed))))
        encoded = zlib.compress(source, 9).encode('base64').replace('\n', '')
        # We can't use bytes.decode() in 3.x since it was restricted to always
        # return unicode, so codecs.decode() is used instead. In 3.x
        # codecs.decode() requires a bytes object. Since we must be compatible
        # with 2.4 (no bytes literal), an extra .encode() either returns the
        # same str (2.x) or an equivalent bytes (3.x).
        return [
            self.python_path, '-c',
            'import codecs,os,sys;_=codecs.decode;'
            'exec(_(_("%s".encode(),"base64"),"zip"))' % (encoded,)
        ]

    def get_preamble(self):
        parent_ids = mitogen.parent_ids[:]
        parent_ids.insert(0, mitogen.context_id)

        source = inspect.getsource(mitogen.core)
        source += '\nExternalContext().main(**%r)\n' % ({
            'parent_ids': parent_ids,
            'context_id': self.remote_id,
            'debug': self.debug,
            'profiling': self.profiling,
            'log_level': get_log_level(),
            'whitelist': self._router.get_module_whitelist(),
            'blacklist': self._router.get_module_blacklist(),
        },)

        return zlib.compress(minimize_source(source), 9)

    create_child = staticmethod(create_child)

    def connect(self):
        LOG.debug('%r.connect()', self)
        pid, fd = self.create_child(*self.get_boot_command())
        self.name = 'local.%s' % (pid,)
        self.receive_side = mitogen.core.Side(self, fd)
        self.transmit_side = mitogen.core.Side(self, os.dup(fd))
        LOG.debug('%r.connect(): child process stdin/stdout=%r',
                  self, self.receive_side.fd)

        self._connect_bootstrap()

    def _ec0_received(self):
        LOG.debug('%r._ec0_received()', self)
        write_all(self.transmit_side.fd, self.get_preamble())
        discard_until(self.receive_side.fd, 'EC1\n', time.time() + 10.0)

    def _connect_bootstrap(self):
        deadline = time.time() + self.connect_timeout
        discard_until(self.receive_side.fd, 'EC0\n', deadline)
        self._ec0_received()


class ChildIdAllocator(object):
    def __init__(self, router):
        self.router = router

    def allocate(self):
        master = mitogen.core.Context(self.router, 0)
        return master.send_await(
            mitogen.core.Message(dst_id=0, handle=mitogen.core.ALLOCATE_ID)
        )


class Router(mitogen.core.Router):
    context_class = mitogen.core.Context

    def get_module_blacklist(self):
        if mitogen.context_id == 0:
            return self.responder.blacklist
        return self.importer.blacklist

    def get_module_whitelist(self):
        if mitogen.context_id == 0:
            return self.responder.whitelist
        return self.importer.whitelist

    def allocate_id(self):
        return self.id_allocator.allocate()

    def context_by_id(self, context_id, via_id=None):
        context = self._context_by_id.get(context_id)
        if context is None:
            context = self.context_class(self, context_id)
            if via_id is not None:
                context.via = self.context_by_id(via_id)
            self._context_by_id[context_id] = context
        return context

    def _connect(self, context_id, klass, name=None, **kwargs):
        context = self.context_class(self, context_id)
        stream = klass(self, context.context_id, **kwargs)
        if name is not None:
            stream.name = name
        stream.connect()
        context.name = stream.name
        self.register(context, stream)
        return context

    def connect(self, method_name, name=None, **kwargs):
        klass = METHOD_NAMES[method_name]()
        kwargs.setdefault('debug', self.debug)
        kwargs.setdefault('profiling', self.profiling)

        via = kwargs.pop('via', None)
        if via is not None:
            return self.proxy_connect(via, method_name, name=name, **kwargs)
        context_id = self.allocate_id()
        return self._connect(context_id, klass, name=name, **kwargs)

    def proxy_connect(self, via_context, method_name, name=None, **kwargs):
        context_id = self.allocate_id()
        # Must be added prior to _proxy_connect() to avoid a race.
        self.add_route(context_id, via_context.context_id)
        name = via_context.call(_proxy_connect,
            name, context_id, method_name, kwargs
        )
        name = '%s.%s' % (via_context.name, name)

        context = self.context_class(self, context_id, name=name)
        context.via = via_context
        self._context_by_id[context.context_id] = context

        self.propagate_route(context, via_context)
        return context


class ProcessMonitor(object):
    def __init__(self):
        # pid -> callback()
        self.callback_by_pid = {}
        signal.signal(signal.SIGCHLD, self._on_sigchld)

    def _on_sigchld(self, _signum, _frame):
        for pid, callback in self.callback_by_pid.items():
            pid, status = os.waitpid(pid, os.WNOHANG)
            if pid:
                callback(status)
                del self.callback_by_pid[pid]

    def add(self, pid, callback):
        self.callback_by_pid[pid] = callback

    _instance = None

    @classmethod
    def instance(cls):
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance


class ModuleForwarder(object):
    """
    Respond to GET_MODULE requests in a slave by forwarding the request to our
    parent context, or satisfying the request from our local Importer cache.
    """
    def __init__(self, router, parent_context, importer):
        self.router = router
        self.parent_context = parent_context
        self.importer = importer
        router.add_handler(self._on_get_module, mitogen.core.GET_MODULE)

    def __repr__(self):
        return 'ModuleForwarder(%r)' % (self.router,)

    def _on_get_module(self, msg):
        LOG.debug('%r._on_get_module(%r)', self, msg)
        if msg == mitogen.core._DEAD:
            return

        fullname = msg.data
        callback = lambda: self._on_cache_callback(msg, fullname)
        self.importer._request_module(fullname, callback)

    def _send_one_module(self, msg, tup):
        self.router._async_route(
            mitogen.core.Message.pickled(
                tup,
                dst_id=msg.src_id,
                handle=mitogen.core.LOAD_MODULE,
            )
        )

    def _on_cache_callback(self, msg, fullname):
        LOG.debug('%r._on_get_module(): sending %r', self, fullname)
        tup = self.importer._cache[fullname]
        if tup is not None:
            for related in tup[4]:
                rtup = self.importer._cache.get(related)
                if not rtup:
                    LOG.debug('%r._on_get_module(): skipping absent %r',
                               self, related)
                    continue
                self._send_one_module(msg, rtup)

        self._send_one_module(msg, tup)
