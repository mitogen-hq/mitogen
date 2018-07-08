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

"""
This module defines functionality common to master and parent processes. It is
sent to any child context that is due to become a parent, due to recursive
connection.
"""

import codecs
import errno
import fcntl
import getpass
import inspect
import logging
import os
import signal
import socket
import subprocess
import sys
import termios
import textwrap
import threading
import time
import types
import zlib

# Absolute imports for <2.5.
select = __import__('select')

try:
    from cStringIO import StringIO
except ImportError:
    from io import StringIO

try:
    from functools import lru_cache
except ImportError:
    from mitogen.compat.functools import lru_cache

import mitogen.core
from mitogen.core import b
from mitogen.core import LOG
from mitogen.core import IOLOG


if mitogen.core.PY3:
    xrange = range

try:
    SC_OPEN_MAX = os.sysconf('SC_OPEN_MAX')
except:
    SC_OPEN_MAX = 1024


def get_log_level():
    return (LOG.level or logging.getLogger().level or logging.INFO)


def get_core_source():
    """
    In non-masters, simply fetch the cached mitogen.core source code via the
    import mechanism. In masters, this function is replaced with a version that
    performs minification directly.
    """
    return inspect.getsource(mitogen.core)


def is_immediate_child(msg, stream):
    """
    Handler policy that requires messages to arrive only from immediately
    connected children.
    """
    return msg.src_id == stream.remote_id


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
    for fd in xrange(3, SC_OPEN_MAX):
        try:
            os.close(fd)
        except OSError:
            pass


def create_socketpair():
    parentfp, childfp = socket.socketpair()
    parentfp.setsockopt(socket.SOL_SOCKET,
                        socket.SO_SNDBUF,
                        mitogen.core.CHUNK_SIZE)
    childfp.setsockopt(socket.SOL_SOCKET,
                       socket.SO_RCVBUF,
                       mitogen.core.CHUNK_SIZE)
    return parentfp, childfp


def create_child(args, merge_stdio=False, preexec_fn=None):
    """
    Create a child process whose stdin/stdout is connected to a socket.

    :param args:
        Argument vector for execv() call.
    :param bool merge_stdio:
        If :data:`True`, arrange for `stderr` to be connected to the `stdout`
        socketpair, rather than inherited from the parent process. This may be
        necessary to ensure that not TTY is connected to any stdio handle, for
        instance when using LXC.
    :returns:
        `(pid, socket_obj, :data:`None`)`
    """
    parentfp, childfp = create_socketpair()
    # When running under a monkey patches-enabled gevent, the socket module
    # yields file descriptors who already have O_NONBLOCK, which is
    # persisted across fork, totally breaking Python. Therefore, drop
    # O_NONBLOCK from Python's future stdin fd.
    mitogen.core.set_block(childfp.fileno())

    if merge_stdio:
        extra = {'stderr': childfp}
    else:
        extra = {}

    proc = subprocess.Popen(
        args=args,
        stdin=childfp,
        stdout=childfp,
        close_fds=True,
        preexec_fn=preexec_fn,
        **extra
    )
    childfp.close()
    # Decouple the socket from the lifetime of the Python socket object.
    fd = os.dup(parentfp.fileno())
    parentfp.close()

    LOG.debug('create_child() child %d fd %d, parent %d, cmd: %s',
              proc.pid, fd, os.getpid(), Argv(args))
    return proc.pid, fd, None


def _acquire_controlling_tty():
    os.setsid()
    if sys.platform == 'linux2':
        # On Linux, the controlling tty becomes the first tty opened by a
        # process lacking any prior tty.
        os.close(os.open(os.ttyname(2), os.O_RDWR))
    if hasattr(termios, 'TIOCSCTTY'):
        # On BSD an explicit ioctl is required. For some inexplicable reason,
        # Python 2.6 on Travis also requires it.
        fcntl.ioctl(2, termios.TIOCSCTTY)


def tty_create_child(args):
    """
    Return a file descriptor connected to the master end of a pseudo-terminal,
    whose slave end is connected to stdin/stdout/stderr of a new child process.
    The child is created such that the pseudo-terminal becomes its controlling
    TTY, ensuring access to /dev/tty returns a new file descriptor open on the
    slave end.

    :param list args:
        :py:func:`os.execl` argument list.

    :returns:
        `(pid, tty_fd, None)`
    """
    master_fd, slave_fd = os.openpty()
    mitogen.core.set_block(slave_fd)
    disable_echo(master_fd)
    disable_echo(slave_fd)

    proc = subprocess.Popen(
        args=args,
        stdin=slave_fd,
        stdout=slave_fd,
        stderr=slave_fd,
        preexec_fn=_acquire_controlling_tty,
        close_fds=True,
    )

    os.close(slave_fd)
    LOG.debug('tty_create_child() child %d fd %d, parent %d, cmd: %s',
              proc.pid, master_fd, os.getpid(), Argv(args))
    return proc.pid, master_fd, None


def hybrid_tty_create_child(args):
    """
    Like :func:`tty_create_child`, except attach stdin/stdout to a socketpair
    like :func:`create_child`, but leave stderr and the controlling TTY
    attached to a TTY.

    :param list args:
        :py:func:`os.execl` argument list.

    :returns:
        `(pid, socketpair_fd, tty_fd)`
    """
    master_fd, slave_fd = os.openpty()
    parentfp, childfp = create_socketpair()

    mitogen.core.set_block(slave_fd)
    mitogen.core.set_block(childfp)
    disable_echo(master_fd)
    disable_echo(slave_fd)
    proc = subprocess.Popen(
        args=args,
        stdin=childfp,
        stdout=childfp,
        stderr=slave_fd,
        preexec_fn=_acquire_controlling_tty,
        close_fds=True,
    )

    os.close(slave_fd)
    childfp.close()
    # Decouple the socket from the lifetime of the Python socket object.
    stdio_fd = os.dup(parentfp.fileno())
    parentfp.close()

    LOG.debug('hybrid_tty_create_child() pid=%d stdio=%d, tty=%d, cmd: %s',
              proc.pid, stdio_fd, master_fd, Argv(args))
    return proc.pid, stdio_fd, master_fd


def write_all(fd, s, deadline=None):
    timeout = None
    written = 0
    poller = PREFERRED_POLLER()
    poller.start_transmit(fd)

    try:
        while written < len(s):
            if deadline is not None:
                timeout = max(0, deadline - time.time())
            if timeout == 0:
                raise mitogen.core.TimeoutError('write timed out')

            if mitogen.core.PY3:
                window = memoryview(s)[written:]
            else:
                window = buffer(s, written)

            for fd in poller.poll(timeout):
                n, disconnected = mitogen.core.io_op(os.write, fd, window)
                if disconnected:
                    raise mitogen.core.StreamError('EOF on stream during write')

                written += n
    finally:
        poller.close()


def iter_read(fds, deadline=None):
    poller = PREFERRED_POLLER()
    for fd in fds:
        poller.start_receive(fd)

    bits = []
    timeout = None
    try:
        while poller.readers:
            if deadline is not None:
                timeout = max(0, deadline - time.time())
                if timeout == 0:
                    break

            for fd in poller.poll(timeout):
                s, disconnected = mitogen.core.io_op(os.read, fd, 4096)
                if disconnected or not s:
                    IOLOG.debug('iter_read(%r) -> disconnected', fd)
                    poller.stop_receive(fd)
                else:
                    IOLOG.debug('iter_read(%r) -> %r', fd, s)
                    bits.append(s)
                    yield s
    finally:
        poller.close()

    if not poller.readers:
        raise mitogen.core.StreamError(
            u'EOF on stream; last 300 bytes received: %r' %
            (b('').join(bits)[-300:].decode('latin1'),)
        )
    raise mitogen.core.TimeoutError('read timed out')


def discard_until(fd, s, deadline):
    for buf in iter_read([fd], deadline):
        if IOLOG.level == logging.DEBUG:
            for line in buf.splitlines():
                IOLOG.debug('discard_until: discarding %r', line)
        if buf.endswith(s):
            return


def _upgrade_broker(broker):
    """
    Extract the poller state from Broker and replace it with the industrial
    strength poller for this OS. Must run on the Broker thread.
    """
    # This function is deadly! The act of calling start_receive() generates log
    # messages which must be silenced as the upgrade progresses, otherwise the
    # poller state will change as it is copied, resulting in write fds that are
    # lost. (Due to LogHandler->Router->Stream->Broker->Poller, where Stream
    # only calls start_transmit() when transitioning from empty to non-empty
    # buffer. If the start_transmit() is lost, writes from the child hang
    # permanently).
    root = logging.getLogger()
    old_level = root.level
    root.setLevel(logging.CRITICAL)

    old = broker.poller
    new = PREFERRED_POLLER()
    for fd, data in old.readers:
        new.start_receive(fd, data)
    for fd, data in old.writers:
        new.start_transmit(fd, data)

    old.close()
    broker.poller = new
    root.setLevel(old_level)
    LOG.debug('replaced %r with %r (new: %d readers, %d writers; '
              'old: %d readers, %d writers)', old, new,
              len(new.readers), len(new.writers),
              len(old.readers), len(old.writers))


def upgrade_router(econtext):
    if not isinstance(econtext.router, Router):  # TODO
        econtext.broker.defer(_upgrade_broker, econtext.broker)
        econtext.router.__class__ = Router  # TODO
        econtext.router.upgrade(
            importer=econtext.importer,
            parent=econtext.parent,
        )


def make_call_msg(fn, *args, **kwargs):
    if isinstance(fn, types.MethodType) and \
       isinstance(fn.im_self, (type, types.ClassType)):
        klass = mitogen.core.to_text(fn.im_self.__name__)
    else:
        klass = None

    tup = (
        mitogen.core.to_text(fn.__module__),
        klass,
        mitogen.core.to_text(fn.__name__),
        args,
        mitogen.core.Kwargs(kwargs)
    )
    return mitogen.core.Message.pickled(tup, handle=mitogen.core.CALL_FUNCTION)


def stream_by_method_name(name):
    """
    Given the name of a Mitogen connection method, import its implementation
    module and return its Stream subclass.
    """
    if name == u'local':
        name = u'parent'
    module = mitogen.core.import_module(u'mitogen.' + name)
    return module.Stream


@mitogen.core.takes_econtext
def _proxy_connect(name, method_name, kwargs, econtext):
    upgrade_router(econtext)
    try:
        context = econtext.router._connect(
            klass=stream_by_method_name(method_name),
            name=name,
            **kwargs
        )
    except mitogen.core.StreamError:
        return {
            u'id': None,
            u'name': None,
            u'msg': 'error occurred on host %s: %s' % (
                socket.gethostname(),
                sys.exc_info()[1],
            ),
        }

    return {
        u'id': context.context_id,
        u'name': context.name,
        u'msg': None,
    }


class Argv(object):
    """
    Wrapper to defer argv formatting when debug logging is disabled.
    """
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


class CallSpec(object):
    """
    Wrapper to defer call argument formatting when debug logging is disabled.
    """
    def __init__(self, func, args, kwargs):
        self.func = func
        self.args = args
        self.kwargs = kwargs

    def _get_name(self):
        return u'%s.%s' % (self.func.__module__,
                           self.func.__name__)

    def _get_args(self):
        return u', '.join(repr(a) for a in self.args)

    def _get_kwargs(self):
        s = u''
        if self.kwargs:
            s = u', '.join('%s=%r' % (k, v) for k, v in self.kwargs.items())
            if self.args:
                s = u', ' + s
        return s

    def __repr__(self):
        return '%s(%s%s)' % (
            self._get_name(),
            self._get_args(),
            self._get_kwargs(),
        )


class KqueuePoller(mitogen.core.Poller):
    _repr = 'KqueuePoller()'

    def __init__(self):
        self._kqueue = select.kqueue()
        self._rfds = {}
        self._wfds = {}
        self._changelist = []

    def close(self):
        self._kqueue.close()

    @property
    def readers(self):
        return list(self._rfds.items())

    @property
    def writers(self):
        return list(self._wfds.items())

    def _control(self, fd, filters, flags):
        mitogen.core._vv and IOLOG.debug(
            '%r._control(%r, %r, %r)', self, fd, filters, flags)
        self._changelist.append(select.kevent(fd, filters, flags))

    def start_receive(self, fd, data=None):
        mitogen.core._vv and IOLOG.debug('%r.start_receive(%r, %r)',
            self, fd, data)
        if fd not in self._rfds:
            self._control(fd, select.KQ_FILTER_READ, select.KQ_EV_ADD)
        self._rfds[fd] = data or fd

    def stop_receive(self, fd):
        mitogen.core._vv and IOLOG.debug('%r.stop_receive(%r)', self, fd)
        if fd in self._rfds:
            self._control(fd, select.KQ_FILTER_READ, select.KQ_EV_DELETE)
            del self._rfds[fd]

    def start_transmit(self, fd, data=None):
        mitogen.core._vv and IOLOG.debug('%r.start_transmit(%r, %r)',
            self, fd, data)
        if fd not in self._wfds:
            self._control(fd, select.KQ_FILTER_WRITE, select.KQ_EV_ADD)
        self._wfds[fd] = data or fd

    def stop_transmit(self, fd):
        mitogen.core._vv and IOLOG.debug('%r.stop_transmit(%r)', self, fd)
        if fd in self._wfds:
            self._control(fd, select.KQ_FILTER_WRITE, select.KQ_EV_DELETE)
            del self._wfds[fd]

    def poll(self, timeout=None):
        changelist = self._changelist
        self._changelist = []
        events, _ = mitogen.core.io_op(self._kqueue.control,
            changelist, 32, timeout)
        for event in events:
            fd = event.ident
            if event.filter == select.KQ_FILTER_READ and fd in self._rfds:
                # Events can still be read for an already-discarded fd.
                mitogen.core._vv and IOLOG.debug('%r: POLLIN: %r', self, fd)
                yield self._rfds[fd]
            elif event.filter == select.KQ_FILTER_WRITE and fd in self._wfds:
                mitogen.core._vv and IOLOG.debug('%r: POLLOUT: %r', self, fd)
                yield self._wfds[fd]


class EpollPoller(mitogen.core.Poller):
    _repr = 'EpollPoller()'

    def __init__(self):
        self._epoll = select.epoll(32)
        self._registered_fds = set()
        self._rfds = {}
        self._wfds = {}

    def close(self):
        self._epoll.close()

    @property
    def readers(self):
        return list(self._rfds.items())

    @property
    def writers(self):
        return list(self._wfds.items())

    def _control(self, fd):
        mitogen.core._vv and IOLOG.debug('%r._control(%r)', self, fd)
        mask = (((fd in self._rfds) and select.EPOLLIN) |
                ((fd in self._wfds) and select.EPOLLOUT))
        if mask:
            if fd in self._registered_fds:
                self._epoll.modify(fd, mask)
            else:
                self._epoll.register(fd, mask)
                self._registered_fds.add(fd)
        elif fd in self._registered_fds:
            self._epoll.unregister(fd)
            self._registered_fds.remove(fd)

    def start_receive(self, fd, data=None):
        mitogen.core._vv and IOLOG.debug('%r.start_receive(%r, %r)',
            self, fd, data)
        self._rfds[fd] = data or fd
        self._control(fd)

    def stop_receive(self, fd):
        mitogen.core._vv and IOLOG.debug('%r.stop_receive(%r)', self, fd)
        self._rfds.pop(fd, None)
        self._control(fd)

    def start_transmit(self, fd, data=None):
        mitogen.core._vv and IOLOG.debug('%r.start_transmit(%r, %r)',
            self, fd, data)
        self._wfds[fd] = data or fd
        self._control(fd)

    def stop_transmit(self, fd):
        mitogen.core._vv and IOLOG.debug('%r.stop_transmit(%r)', self, fd)
        self._wfds.pop(fd, None)
        self._control(fd)

    _inmask = (getattr(select, 'EPOLLIN', 0) |
               getattr(select, 'EPOLLHUP', 0))

    def poll(self, timeout=None):
        the_timeout = -1
        if timeout is not None:
            the_timeout = timeout

        events, _ = mitogen.core.io_op(self._epoll.poll, the_timeout, 32)
        for fd, event in events:
            if event & self._inmask and fd in self._rfds:
                # Events can still be read for an already-discarded fd.
                mitogen.core._vv and IOLOG.debug('%r: POLLIN: %r', self, fd)
                yield self._rfds[fd]
            if event & select.EPOLLOUT and fd in self._wfds:
                mitogen.core._vv and IOLOG.debug('%r: POLLOUT: %r', self, fd)
                yield self._wfds[fd]


POLLER_BY_SYSNAME = {
    'Darwin': KqueuePoller,
    'FreeBSD': KqueuePoller,
    'Linux': EpollPoller,
}

PREFERRED_POLLER = POLLER_BY_SYSNAME.get(
    os.uname()[0],
    mitogen.core.Poller,
)

# For apps that start threads dynamically, it's possible Latch will also get
# very high-numbered wait fds when there are many connections, and so select()
# becomes useless there too. So swap in our favourite poller.
mitogen.core.Latch.poller_class = PREFERRED_POLLER


class TtyLogStream(mitogen.core.BasicStream):
    """
    For "hybrid TTY/socketpair" mode, after a connection has been setup, a
    spare TTY file descriptor will exist that cannot be closed, and to which
    SSH or sudo may continue writing log messages.

    The descriptor cannot be closed since the UNIX TTY layer will send a
    termination signal to any processes whose controlling TTY is the TTY that
    has been closed.

    TtyLogStream takes over this descriptor and creates corresponding log
    messages for anything written to it.
    """

    def __init__(self, tty_fd, stream):
        self.receive_side = mitogen.core.Side(self, tty_fd)
        self.transmit_side = self.receive_side
        self.stream = stream
        self.buf = ''

    def __repr__(self):
        return 'mitogen.parent.TtyLogStream(%r)' % (self.stream.name,)

    def on_receive(self, broker):
        """
        This handler is only called after the stream is registered with the IO
        loop, the descriptor is manually read/written by _connect_bootstrap()
        prior to that.
        """
        buf = self.receive_side.read()
        if not buf:
            return self.on_disconnect(broker)

        self.buf += buf.decode('utf-8', 'replace')
        while '\n' in self.buf:
            lines = self.buf.split('\n')
            self.buf = lines[-1]
            for line in lines[:-1]:
                LOG.debug('%r:  %r', self, line.rstrip())


class Stream(mitogen.core.Stream):
    """
    Base for streams capable of starting new slaves.
    """
    #: The path to the remote Python interpreter.
    python_path = sys.executable

    #: Maximum time to wait for a connection attempt.
    connect_timeout = 30.0

    #: Derived from :py:attr:`connect_timeout`; absolute floating point
    #: UNIX timestamp after which the connection attempt should be abandoned.
    connect_deadline = None

    #: True to cause context to write verbose /tmp/mitogen.<pid>.log.
    debug = False

    #: True to cause context to write /tmp/mitogen.stats.<pid>.<thread>.log.
    profiling = False

    #: Set to the child's PID by connect().
    pid = None

    #: Passed via Router wrapper methods, must eventually be passed to
    #: ExternalContext.main().
    max_message_size = None

    def __init__(self, *args, **kwargs):
        super(Stream, self).__init__(*args, **kwargs)
        self.sent_modules = set(['mitogen', 'mitogen.core'])
        #: List of contexts reachable via this stream; used to cleanup routes
        #: during disconnection.
        self.routes = set([self.remote_id])

    def construct(self, max_message_size, remote_name=None, python_path=None,
                  debug=False, connect_timeout=None, profiling=False,
                  unidirectional=False, old_router=None, **kwargs):
        """Get the named context running on the local machine, creating it if
        it does not exist."""
        super(Stream, self).construct(**kwargs)
        self.max_message_size = max_message_size
        if python_path:
            self.python_path = python_path
        if connect_timeout:
            self.connect_timeout = connect_timeout
        if remote_name is None:
            remote_name = '%s@%s:%d'
            remote_name %= (getpass.getuser(), socket.gethostname(), os.getpid())
        if '/' in remote_name or '\\' in remote_name:
            raise ValueError('remote_name= cannot contain slashes')
        self.remote_name = remote_name
        self.debug = debug
        self.profiling = profiling
        self.unidirectional = unidirectional
        self.max_message_size = max_message_size
        self.connect_deadline = time.time() + self.connect_timeout

    def on_shutdown(self, broker):
        """Request the slave gracefully shut itself down."""
        LOG.debug('%r closing CALL_FUNCTION channel', self)
        self._send(
            mitogen.core.Message(
                src_id=mitogen.context_id,
                dst_id=self.remote_id,
                handle=mitogen.core.SHUTDOWN,
            )
        )

    #: If :data:`True`, indicates the subprocess managed by us should not be
    #: killed during graceful detachment, as it the actual process implementing
    #: the child context. In all other cases, the subprocess is SSH, sudo, or a
    #: similar tool that should be reminded to quit during disconnection.
    child_is_immediate_subprocess = True

    detached = False
    _reaped = False

    def _reap_child(self):
        """
        Reap the child process during disconnection.
        """
        if self.detached and self.child_is_immediate_subprocess:
            LOG.debug('%r: immediate child is detached, won\'t reap it', self)
            return

        if self._reaped:
            # on_disconnect() may be invoked more than once, for example, if
            # there is still a pending message to be sent after the first
            # on_disconnect() call.
            return

        try:
            pid, status = os.waitpid(self.pid, os.WNOHANG)
        except OSError:
            e = sys.exc_info()[1]
            if e.args[0] == errno.ECHILD:
                LOG.warn('%r: waitpid(%r) produced ECHILD', self, self.pid)
                return
            raise

        self._reaped = True
        if pid:
            LOG.debug('%r: child process exit status was %d', self, status)
            return

        # For processes like sudo we cannot actually send sudo a signal,
        # because it is setuid, so this is best-effort only.
        LOG.debug('%r: child process still alive, sending SIGTERM', self)
        try:
            os.kill(self.pid, signal.SIGTERM)
        except OSError:
            e = sys.exc_info()[1]
            if e.args[0] != errno.EPERM:
                raise

    def on_disconnect(self, broker):
        self._reap_child()
        super(Stream, self).on_disconnect(broker)

    # Minimised, gzipped, base64'd and passed to 'python -c'. It forks, dups
    # file descriptor 0 as 100, creates a pipe, then execs a new interpreter
    # with a custom argv.
    #   * Optimized for minimum byte count after minification & compression.
    #   * 'CONTEXT_NAME' and 'PREAMBLE_COMPRESSED_LEN' are substituted with
    #     their respective values.
    #   * CONTEXT_NAME must be prefixed with the name of the Python binary in
    #     order to allow virtualenvs to detect their install prefix.
    #   * For Darwin, OS X installs a craptacular argv0-introspecting Python
    #     version switcher as /usr/bin/python. Override attempts to call it
    #     with an explicit call to python2.7
    #
    # Locals:
    #   R: read side of interpreter stdin.
    #   W: write side of interpreter stdin.
    #   r: read side of core_src FD.
    #   w: write side of core_src FD.
    #   C: the decompressed core source.
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
            if sys.platform == 'darwin' and sys.executable == '/usr/bin/python':
                sys.executable += sys.version[:3]
            os.environ['ARGV0']=sys.executable
            os.execl(sys.executable,sys.executable+'(mitogen:CONTEXT_NAME)')
        os.write(1,'MITO000\n'.encode())
        C=_(os.fdopen(0,'rb').read(PREAMBLE_COMPRESSED_LEN),'zip')
        fp=os.fdopen(W,'wb',0)
        fp.write(C)
        fp.close()
        fp=os.fdopen(w,'wb',0)
        fp.write(C)
        fp.close()
        os.write(1,'MITO001\n'.encode())

    def get_boot_command(self):
        source = inspect.getsource(self._first_stage)
        source = textwrap.dedent('\n'.join(source.strip().split('\n')[2:]))
        source = source.replace('    ', '\t')
        source = source.replace('CONTEXT_NAME', self.remote_name)
        preamble_compressed = self.get_preamble()
        source = source.replace('PREAMBLE_COMPRESSED_LEN',
                                str(len(preamble_compressed)))
        compressed = zlib.compress(source.encode(), 9)
        encoded = codecs.encode(compressed, 'base64').replace(b('\n'), b(''))
        # We can't use bytes.decode() in 3.x since it was restricted to always
        # return unicode, so codecs.decode() is used instead. In 3.x
        # codecs.decode() requires a bytes object. Since we must be compatible
        # with 2.4 (no bytes literal), an extra .encode() either returns the
        # same str (2.x) or an equivalent bytes (3.x).
        return [
            self.python_path, '-c',
            'import codecs,os,sys;_=codecs.decode;'
            'exec(_(_("%s".encode(),"base64"),"zip"))' % (encoded.decode(),)
        ]

    def get_econtext_config(self):
        assert self.max_message_size is not None
        parent_ids = mitogen.parent_ids[:]
        parent_ids.insert(0, mitogen.context_id)
        return {
            'parent_ids': parent_ids,
            'context_id': self.remote_id,
            'debug': self.debug,
            'profiling': self.profiling,
            'unidirectional': self.unidirectional,
            'log_level': get_log_level(),
            'whitelist': self._router.get_module_whitelist(),
            'blacklist': self._router.get_module_blacklist(),
            'max_message_size': self.max_message_size,
            'version': mitogen.__version__,
        }

    def get_preamble(self):
        source = get_core_source()
        source += '\nExternalContext(%r).main()\n' % (
            self.get_econtext_config(),
        )
        return zlib.compress(source.encode('utf-8'), 9)

    create_child = staticmethod(create_child)
    create_child_args = {}
    name_prefix = u'local'

    def start_child(self):
        args = self.get_boot_command()
        try:
            return self.create_child(args, **self.create_child_args)
        except OSError:
            e = sys.exc_info()[1]
            msg = 'Child start failed: %s. Command was: %s' % (e, Argv(args))
            raise mitogen.core.StreamError(msg)

    def connect(self):
        LOG.debug('%r.connect()', self)
        self.pid, fd, extra_fd = self.start_child()
        self.name = u'%s.%s' % (self.name_prefix, self.pid)
        self.receive_side = mitogen.core.Side(self, fd)
        self.transmit_side = mitogen.core.Side(self, os.dup(fd))
        LOG.debug('%r.connect(): child process stdin/stdout=%r',
                  self, self.receive_side.fd)

        try:
            self._connect_bootstrap(extra_fd)
        except Exception:
            self._reap_child()
            raise

    #: For ssh.py, this must be at least max(len('password'), len('debug1:'))
    EC0_MARKER = mitogen.core.b('MITO000\n')
    EC1_MARKER = mitogen.core.b('MITO001\n')

    def _ec0_received(self):
        LOG.debug('%r._ec0_received()', self)
        write_all(self.transmit_side.fd, self.get_preamble())
        discard_until(self.receive_side.fd, self.EC1_MARKER,
                      self.connect_deadline)

    def _connect_bootstrap(self, extra_fd):
        discard_until(self.receive_side.fd, self.EC0_MARKER,
                      self.connect_deadline)
        self._ec0_received()


class ChildIdAllocator(object):
    def __init__(self, router):
        self.router = router
        self.lock = threading.Lock()
        self.it = iter(xrange(0))

    def allocate(self):
        self.lock.acquire()
        try:
            for id_ in self.it:
                return id_

            master = mitogen.core.Context(self.router, 0)
            start, end = master.send_await(
                mitogen.core.Message(dst_id=0, handle=mitogen.core.ALLOCATE_ID)
            )
            self.it = iter(xrange(start, end))
        finally:
            self.lock.release()

        return self.allocate()


class Context(mitogen.core.Context):
    via = None

    def __eq__(self, other):
        return (isinstance(other, mitogen.core.Context) and
                (other.context_id == self.context_id) and
                (other.router == self.router))

    def __hash__(self):
        return hash((self.router, self.context_id))

    def call_async(self, fn, *args, **kwargs):
        LOG.debug('%r.call_async(): %r', self, CallSpec(fn, args, kwargs))
        return self.send_async(make_call_msg(fn, *args, **kwargs))

    def call(self, fn, *args, **kwargs):
        receiver = self.call_async(fn, *args, **kwargs)
        return receiver.get().unpickle(throw_dead=False)

    def call_no_reply(self, fn, *args, **kwargs):
        LOG.debug('%r.call_no_reply(%r, *%r, **%r)',
                  self, fn, args, kwargs)
        self.send(make_call_msg(fn, *args, **kwargs))

    def shutdown(self, wait=False):
        LOG.debug('%r.shutdown() sending SHUTDOWN', self)
        latch = mitogen.core.Latch()
        mitogen.core.listen(self, 'disconnect', lambda: latch.put(None))
        self.send(
            mitogen.core.Message(
                handle=mitogen.core.SHUTDOWN,
            )
        )

        if wait:
            latch.get()
        else:
            return latch


class RouteMonitor(object):
    def __init__(self, router, parent=None):
        self.router = router
        self.parent = parent
        self.router.add_handler(
            fn=self._on_add_route,
            handle=mitogen.core.ADD_ROUTE,
            persist=True,
            policy=is_immediate_child,
        )
        self.router.add_handler(
            fn=self._on_del_route,
            handle=mitogen.core.DEL_ROUTE,
            persist=True,
            policy=is_immediate_child,
        )

    def propagate(self, handle, target_id, name=None):
        # self.parent is None in the master.
        if not self.parent:
            return

        data = str(target_id)
        if name:
            data = '%s:%s' % (target_id, mitogen.core.b(name))
        self.parent.send(
            mitogen.core.Message(
                handle=handle,
                data=data.encode('utf-8'),
            )
        )

    def notice_stream(self, stream):
        """
        When this parent is responsible for a new directly connected child
        stream, we're also responsible for broadcasting DEL_ROUTE upstream
        if/when that child disconnects.
        """
        self.propagate(mitogen.core.ADD_ROUTE, stream.remote_id,
                       stream.name)
        mitogen.core.listen(
            obj=stream,
            name='disconnect',
            func=lambda: self._on_stream_disconnect(stream),
        )

    def _on_stream_disconnect(self, stream):
        """
        Respond to disconnection of a local stream by
        """
        LOG.debug('%r is gone; propagating DEL_ROUTE for %r',
                  stream, stream.routes)
        for target_id in stream.routes:
            self.router.del_route(target_id)
            self.propagate(mitogen.core.DEL_ROUTE, target_id)

            context = self.router.context_by_id(target_id, create=False)
            if context:
                mitogen.core.fire(context, 'disconnect')

    def _on_add_route(self, msg):
        if msg.is_dead:
            return

        target_id_s, _, target_name = msg.data.partition(b(':'))
        target_name = target_name.decode()
        target_id = int(target_id_s)
        self.router.context_by_id(target_id).name = target_name
        stream = self.router.stream_by_id(msg.auth_id)
        current = self.router.stream_by_id(target_id)
        if current and current.remote_id != mitogen.parent_id:
            LOG.error('Cannot add duplicate route to %r via %r, '
                      'already have existing route via %r',
                      target_id, stream, current)
            return

        LOG.debug('Adding route to %d via %r', target_id, stream)
        stream.routes.add(target_id)
        self.router.add_route(target_id, stream)
        self.propagate(mitogen.core.ADD_ROUTE, target_id, target_name)

    def _on_del_route(self, msg):
        if msg.is_dead:
            return

        target_id = int(msg.data)
        registered_stream = self.router.stream_by_id(target_id)
        stream = self.router.stream_by_id(msg.auth_id)
        if registered_stream != stream:
            LOG.error('Received DEL_ROUTE for %d from %r, expected %r',
                      target_id, stream, registered_stream)
            return

        LOG.debug('Deleting route to %d via %r', target_id, stream)
        stream.routes.discard(target_id)
        self.router.del_route(target_id)
        self.propagate(mitogen.core.DEL_ROUTE, target_id)
        context = self.router.context_by_id(target_id, create=False)
        if context:
            mitogen.core.fire(context, 'disconnect')


class Router(mitogen.core.Router):
    context_class = Context
    debug = False
    profiling = False

    id_allocator = None
    responder = None
    log_forwarder = None
    route_monitor = None

    def upgrade(self, importer, parent):
        LOG.debug('%r.upgrade()', self)
        self.id_allocator = ChildIdAllocator(router=self)
        self.responder = ModuleForwarder(
            router=self,
            parent_context=parent,
            importer=importer,
        )
        self.route_monitor = RouteMonitor(self, parent)
        self.add_handler(
            fn=self._on_detaching,
            handle=mitogen.core.DETACHING,
            persist=True,
        )

    def _on_detaching(self, msg):
        if msg.is_dead:
            return
        stream = self.stream_by_id(msg.src_id)
        if stream.remote_id != msg.src_id or stream.detached:
            LOG.warning('bad DETACHING received on %r: %r', stream, msg)
            return
        LOG.debug('%r: marking as detached', stream)
        stream.detached = True
        msg.reply(None)

    def add_route(self, target_id, stream):
        LOG.debug('%r.add_route(%r, %r)', self, target_id, stream)
        assert isinstance(target_id, int)
        assert isinstance(stream, Stream)
        try:
            self._stream_by_id[target_id] = stream
        except KeyError:
            LOG.error('%r: cant add route to %r via %r: no such stream',
                      self, target_id, stream)

    def del_route(self, target_id):
        LOG.debug('%r.del_route(%r)', self, target_id)
        try:
            del self._stream_by_id[target_id]
        except KeyError:
            LOG.error('%r: cant delete route to %r: no such stream',
                      self, target_id)

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

    def context_by_id(self, context_id, via_id=None, create=True):
        context = self._context_by_id.get(context_id)
        if create and not context:
            context = self.context_class(self, context_id)
            if via_id is not None:
                context.via = self.context_by_id(via_id)
            self._context_by_id[context_id] = context
        return context

    connection_timeout_msg = u"Connection timed out."

    def _connect(self, klass, name=None, **kwargs):
        context_id = self.allocate_id()
        context = self.context_class(self, context_id)
        kwargs['old_router'] = self
        kwargs['max_message_size'] = self.max_message_size
        stream = klass(self, context_id, **kwargs)
        if name is not None:
            stream.name = name
        try:
            stream.connect()
        except mitogen.core.TimeoutError:
            raise mitogen.core.StreamError(self.connection_timeout_msg)
        context.name = stream.name
        self.route_monitor.notice_stream(stream)
        self.register(context, stream)
        return context

    def connect(self, method_name, name=None, **kwargs):
        klass = stream_by_method_name(method_name)
        kwargs.setdefault(u'debug', self.debug)
        kwargs.setdefault(u'profiling', self.profiling)
        kwargs.setdefault(u'unidirectional', self.unidirectional)

        via = kwargs.pop(u'via', None)
        if via is not None:
            return self.proxy_connect(via, method_name, name=name, **kwargs)
        return self._connect(klass, name=name, **kwargs)

    def proxy_connect(self, via_context, method_name, name=None, **kwargs):
        resp = via_context.call(_proxy_connect,
            name=name,
            method_name=method_name,
            kwargs=mitogen.core.Kwargs(kwargs),
        )
        if resp['msg'] is not None:
            raise mitogen.core.StreamError(resp['msg'])

        name = u'%s.%s' % (via_context.name, resp['name'])
        context = self.context_class(self, resp['id'], name=name)
        context.via = via_context
        self._context_by_id[context.context_id] = context
        return context

    def docker(self, **kwargs):
        return self.connect(u'docker', **kwargs)

    def fork(self, **kwargs):
        return self.connect(u'fork', **kwargs)

    def jail(self, **kwargs):
        return self.connect(u'jail', **kwargs)

    def local(self, **kwargs):
        return self.connect(u'local', **kwargs)

    def lxc(self, **kwargs):
        return self.connect(u'lxc', **kwargs)

    def setns(self, **kwargs):
        return self.connect(u'setns', **kwargs)

    def su(self, **kwargs):
        return self.connect(u'su', **kwargs)

    def sudo(self, **kwargs):
        return self.connect(u'sudo', **kwargs)

    def ssh(self, **kwargs):
        return self.connect(u'ssh', **kwargs)


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
        router.add_handler(
            fn=self._on_forward_module,
            handle=mitogen.core.FORWARD_MODULE,
            persist=True,
            policy=mitogen.core.has_parent_authority,
        )
        router.add_handler(
            fn=self._on_get_module,
            handle=mitogen.core.GET_MODULE,
            persist=True,
            policy=is_immediate_child,
        )

    def __repr__(self):
        return 'ModuleForwarder(%r)' % (self.router,)

    def _on_forward_module(self, msg):
        if msg.is_dead:
            return

        context_id_s, _, fullname = msg.data.partition(b('\x00'))
        fullname = mitogen.core.to_text(fullname)
        context_id = int(context_id_s)
        stream = self.router.stream_by_id(context_id)
        if stream.remote_id == mitogen.parent_id:
            LOG.error('%r: dropping FORWARD_MODULE(%d, %r): no route to child',
                      self, context_id, fullname)
            return

        if fullname in stream.sent_modules:
            return

        LOG.debug('%r._on_forward_module() sending %r to %r via %r',
                  self, fullname, context_id, stream.remote_id)
        self._send_module_and_related(stream, fullname)
        if stream.remote_id != context_id:
            stream._send(
                mitogen.core.Message(
                    data=msg.data,
                    handle=mitogen.core.FORWARD_MODULE,
                    dst_id=stream.remote_id,
                )
            )

    def _on_get_module(self, msg):
        LOG.debug('%r._on_get_module(%r)', self, msg)
        if msg.is_dead:
            return

        fullname = msg.data.decode('utf-8')
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
        stream = self.router.stream_by_id(msg.src_id)
        self._send_module_and_related(stream, fullname)

    def _send_module_and_related(self, stream, fullname):
        tup = self.importer._cache[fullname]
        for related in tup[4]:
            rtup = self.importer._cache.get(related)
            if rtup:
                self._send_one_module(stream, rtup)
            else:
                LOG.debug('%r._send_module_and_related(%r): absent: %r',
                           self, fullname, related)

        self._send_one_module(stream, tup)

    def _send_one_module(self, stream, tup):
        if tup[0] not in stream.sent_modules:
            stream.sent_modules.add(tup[0])
            self.router._async_route(
                mitogen.core.Message.pickled(
                    tup,
                    dst_id=stream.remote_id,
                    handle=mitogen.core.LOAD_MODULE,
                )
            )
