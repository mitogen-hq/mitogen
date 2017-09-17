"""
This module implements functionality required by master processes, such as
starting new contexts via SSH. Its size is also restricted, since it must be
sent to any context that will be used to establish additional child contexts.
"""

import errno
import getpass
import imp
import inspect
import itertools
import logging
import os
import pkgutil
import pty
import re
import select
import signal
import socket
import sys
import termios
import textwrap
import time
import types
import zlib

if not hasattr(pkgutil, 'find_loader'):
    # find_loader() was new in >=2.5, but the modern pkgutil.py syntax has
    # been kept intentionally 2.3 compatible so we can reuse it.
    from mitogen.compat import pkgutil

import mitogen.core


LOG = logging.getLogger('mitogen')
RLOG = logging.getLogger('mitogen.ctx')

DOCSTRING_RE = re.compile(r'""".+?"""', re.M | re.S)
COMMENT_RE = re.compile(r'^[ ]*#[^\n]*$', re.M)
IOLOG_RE = re.compile(r'^[ ]*IOLOG.debug\(.+?\)$', re.M)


def minimize_source(source):
    """Remove comments and docstrings from Python `source`, preserving line
    numbers and syntax of empty blocks."""
    subber = lambda match: '""' + ('\n' * match.group(0).count('\n'))
    source = DOCSTRING_RE.sub(subber, source)
    source = COMMENT_RE.sub('', source)
    return source.replace('    ', '\t')


def get_child_modules(path, fullname):
    """Return the canonical names of all submodules of a package `module`."""
    it = pkgutil.iter_modules([os.path.dirname(path)])
    return ['%s.%s' % (fullname, name) for _, name, _ in it]


def create_child(*args):
    """Create a child process whose stdin/stdout is connected to a socket,
    returning `(pid, socket_obj)`."""
    parentfp, childfp = socket.socketpair()
    pid = os.fork()
    if not pid:
        os.dup2(childfp.fileno(), 0)
        os.dup2(childfp.fileno(), 1)
        childfp.close()
        parentfp.close()
        os.execvp(args[0], args)
        raise SystemExit

    childfp.close()
    LOG.debug('create_child() child %d fd %d, parent %d, args %r',
              pid, parentfp.fileno(), os.getpid(), args)
    return pid, os.dup(parentfp.fileno())


def flags(names):
    """Return the result of ORing a set of (space separated) :py:mod:`termios`
    module constants together."""
    return sum(getattr(termios, name) for name in names.split())


def cfmakeraw((iflag, oflag, cflag, lflag, ispeed, ospeed, cc)):
    """Given a list returned by :py:func:`termios.tcgetattr`, return a list
    that has been modified in the same manner as the `cfmakeraw()` C library
    function."""
    iflag &= ~flags('IGNBRK BRKINT PARMRK ISTRIP INLCR IGNCR ICRNL IXON')
    oflag &= ~flags('OPOST IXOFF')
    lflag &= ~flags('ECHO ECHOE ECHONL ICANON ISIG IEXTEN')
    cflag &= ~flags('CSIZE PARENB')
    cflag |= flags('CS8')

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


def tty_create_child(*args):
    """
    Return a file descriptor connected to the master end of a pseudo-terminal,
    whose slave end is connected to stdin/stdout/stderr of a new child process.
    The child is created such that the pseudo-terminal becomes its controlling
    TTY, ensuring access to /dev/tty returns a new file descriptor open on the
    slave end.

    :param args:
        execl() arguments.
    """
    master_fd, slave_fd = os.openpty()
    disable_echo(master_fd)
    disable_echo(slave_fd)

    pid = os.fork()
    if not pid:
        os.dup2(slave_fd, 0)
        os.dup2(slave_fd, 1)
        os.dup2(slave_fd, 2)
        close_nonstandard_fds()
        os.setsid()
        os.close(os.open(os.ttyname(1), os.O_RDWR))
        os.execvp(args[0], args)
        raise SystemExit

    os.close(slave_fd)
    LOG.debug('tty_create_child() child %d fd %d, parent %d, args %r',
              pid, master_fd, os.getpid(), args)
    return pid, master_fd


def write_all(fd, s):
    written = 0
    while written < len(s):
        rc = os.write(fd, buffer(s, written))
        if not rc:
            raise IOError('short write')
        written += rc
    return written


def read_with_deadline(fd, size, deadline):
    timeout = deadline - time.time()
    if timeout > 0:
        rfds, _, _ = select.select([fd], [], [], timeout)
        if rfds:
            return os.read(fd, size)

    raise mitogen.core.TimeoutError('read timed out')


def iter_read(fd, deadline):
    if deadline is not None:
        LOG.debug('Warning: iter_read(.., deadline=...) unimplemented')

    bits = []
    while True:
        s, disconnected = mitogen.core.io_op(os.read, fd, 4096)
        if disconnected:
            s = ''

        if not s:
            raise mitogen.core.StreamError(
                'EOF on stream; last 300 bytes received: %r' %
                (''.join(bits)[-300:],)
            )

        bits.append(s)
        yield s


def discard_until(fd, s, deadline):
    for buf in iter_read(fd, deadline):
        if buf.endswith(s):
            return


class LogForwarder(object):
    def __init__(self, router):
        self._router = router
        self._cache = {}
        router.add_handler(self._on_forward_log, mitogen.core.FORWARD_LOG)

    def _on_forward_log(self, msg):
        if msg == mitogen.core._DEAD:
            return

        logger = self._cache.get(msg.src_id)
        if logger is None:
            context = self._router.context_by_id(msg.src_id)
            if context is None:
                LOG.error('FORWARD_LOG received from src_id %d', msg.src_id)
                return

            name = '%s.%s' % (RLOG.name, context.name)
            self._cache[msg.src_id] = logger = logging.getLogger(name)

        name, level_s, s = msg.data.split('\x00', 2)
        logger.log(int(level_s), '%s: %s', name, s)

    def __repr__(self):
        return 'LogForwarder(%r)' % (self._router,)


class ModuleResponder(object):
    def __init__(self, router):
        self._router = router
        router.add_handler(self._on_get_module, mitogen.core.GET_MODULE)

    def __repr__(self):
        return 'ModuleResponder(%r)' % (self._router,)

    def _get_module_via_pkgutil(self, fullname):
        """Attempt to fetch source code via pkgutil. In an ideal world, this
        would be the only required implementation of get_module()."""
        loader = pkgutil.find_loader(fullname)
        LOG.debug('pkgutil.find_loader(%r) -> %r', fullname, loader)
        if not loader:
            return

        try:
            path = loader.get_filename(fullname)
            source = loader.get_source(fullname)
            if path is not None and source is not None:
                return path, source, loader.is_package(fullname)
        except AttributeError:
            return

    def _get_module_via_sys_modules(self, fullname):
        """Attempt to fetch source code via sys.modules. This is specifically
        to support __main__, but it may catch a few more cases."""
        if fullname not in sys.modules:
            LOG.debug('%r does not appear in sys.modules', fullname)
            return

        is_pkg = hasattr(sys.modules[fullname], '__path__')
        try:
            source = inspect.getsource(sys.modules[fullname])
        except IOError:
            # Work around inspect.getsourcelines() bug.
            if not is_pkg:
                raise
            source = '\n'

        return (sys.modules[fullname].__file__.rstrip('co'),
                source,
                hasattr(sys.modules[fullname], '__path__'))

    def _get_module_via_parent_enumeration(self, fullname):
        """Attempt to fetch source code by examining the module's (hopefully
        less insane) parent package. Required for ansible.compat.six."""
        pkgname, _, modname = fullname.rpartition('.')
        pkg = sys.modules.get(pkgname)
        if pkg is None or not hasattr(pkg, '__file__'):
            return

        pkg_path = os.path.dirname(pkg.__file__)
        try:
            fp, path, ext = imp.find_module(modname, [pkg_path])
            LOG.error('%r', (fp, path, ext))
            return path, fp.read(), False
        except ImportError, e:
            LOG.debug('imp.find_module(%r, %r) -> %s', modname, [pkg_path], e)

    get_module_methods = [_get_module_via_pkgutil,
                          _get_module_via_sys_modules,
                          _get_module_via_parent_enumeration]

    def _on_get_module(self, msg):
        LOG.debug('%r.get_module(%r)', self, msg)
        if msg == mitogen.core._DEAD:
            return

        fullname = msg.data
        try:
            for method in self.get_module_methods:
                tup = method(self, fullname)
                if tup:
                    break

            try:
                path, source, is_pkg = tup
            except TypeError:
                raise ImportError('could not find %r' % (fullname,))

            LOG.debug('%s found %r: (%r, .., %r)',
                      method.__name__, fullname, path, is_pkg)
            if is_pkg:
                pkg_present = get_child_modules(path, fullname)
                LOG.debug('get_child_modules(%r, %r) -> %r',
                          path, fullname, pkg_present)
            else:
                pkg_present = None

            compressed = zlib.compress(source)
            self._router.route(
                mitogen.core.Message.pickled(
                    (pkg_present, path, compressed),
                    dst_id=msg.src_id,
                    handle=msg.reply_to,
                )
            )
        except Exception:
            LOG.debug('While importing %r', fullname, exc_info=True)
            self._router.route(
                mitogen.core.Message.pickled(
                    None,
                    dst_id=msg.src_id,
                    handle=msg.reply_to,
                )
            )


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
        cached = self.importer._cache.get(fullname)
        if cached:
            LOG.debug('%r._on_get_module(): using cached %r', self, fullname)
            self.router.route(
                mitogen.core.Message.pickled(
                    cached,
                    dst_id=msg.src_id,
                    handle=msg.reply_to,
                )
            )
        else:
            LOG.debug('%r._on_get_module(): requesting %r', self, fullname)
            self.parent_context.send(
                mitogen.core.Message(
                    data=msg.data,
                    handle=mitogen.core.GET_MODULE,
                    reply_to=self.router.add_handler(
                        lambda m: self._on_got_source(m, msg),
                        persist=False
                    )
                )
            )

    def _on_got_source(self, msg, original_msg):
        LOG.debug('%r._on_got_source(%r, %r)', self, msg, original_msg)
        fullname = original_msg.data
        self.importer._cache[fullname] = msg.unpickle()
        self.router.route(
            mitogen.core.Message(
                data=msg.data,
                dst_id=original_msg.src_id,
                handle=original_msg.reply_to,
            )
        )


class Stream(mitogen.core.Stream):
    """
    Base for streams capable of starting new slaves.
    """
    #: The path to the remote Python interpreter.
    python_path = 'python2.7'

    #: True to cause context to write verbose /tmp/mitogen.<pid>.log.
    debug = False

    def construct(self, remote_name=None, python_path=None, debug=False, **kwargs):
        """Get the named context running on the local machine, creating it if
        it does not exist."""
        super(Stream, self).construct(**kwargs)
        if python_path:
            self.python_path = python_path

        if remote_name is None:
            remote_name = '%s@%s:%d'
            remote_name %= (getpass.getuser(), socket.gethostname(), os.getpid())
        self.remote_name = remote_name
        self.debug = debug

    def on_shutdown(self, broker):
        """Request the slave gracefully shut itself down."""
        LOG.debug('%r closing CALL_FUNCTION channel', self)
        self.send(
            mitogen.core.Message.pickled(
                mitogen.core._DEAD,
                src_id=mitogen.context_id,
                dst_id=self.remote_id,
                handle=mitogen.core.CALL_FUNCTION
            )
        )

    # base64'd and passed to 'python -c'. It forks, dups 0->100, creates a
    # pipe, then execs a new interpreter with a custom argv. 'CONTEXT_NAME' is
    # replaced with the context name. Optimized for size.
    def _first_stage():
        import os,sys,zlib
        R,W=os.pipe()
        R2,W2=os.pipe()
        if os.fork():
            os.dup2(0,100)
            os.dup2(R,0)
            os.dup2(R2,101)
            for f in R,R2,W,W2: os.close(f)
            os.environ['ARGV0'] = `[sys.executable]`
            os.execv(sys.executable,['mitogen:CONTEXT_NAME'])
        else:
            os.write(1, 'EC0\n')
            C = zlib.decompress(sys.stdin.read(input()))
            os.fdopen(W,'w',0).write(C)
            os.fdopen(W2,'w',0).write('%s\n%s' % (len(C),C))
            os.write(1, 'EC1\n')
            sys.exit(0)

    def get_boot_command(self):
        source = inspect.getsource(self._first_stage)
        source = textwrap.dedent('\n'.join(source.strip().split('\n')[1:]))
        source = source.replace('    ', '\t')
        source = source.replace('CONTEXT_NAME', self.remote_name)
        encoded = source.encode('base64').replace('\n', '')
        return [self.python_path, '-c',
                'exec("%s".decode("base64"))' % (encoded,)]

    def get_preamble(self):
        source = inspect.getsource(mitogen.core)
        source += '\nExternalContext().main%r\n' % ((
            mitogen.context_id,       # parent_id
            self.remote_id,            # context_id
            self.key,
            self.debug,
            LOG.level or logging.getLogger().level or logging.INFO,
        ),)

        compressed = zlib.compress(minimize_source(source))
        return str(len(compressed)) + '\n' + compressed

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
        discard_until(self.receive_side.fd, 'EC0\n', time.time() + 10.0)
        self._ec0_received()


class Broker(mitogen.core.Broker):
    shutdown_timeout = 5.0


class Context(mitogen.core.Context):
    via = None

    def on_disconnect(self, broker):
        """
        Override base behaviour of triggering Broker shutdown on parent stream
        disconnection.
        """
        mitogen.core.fire(self, 'disconnect')

    def _discard_result(self, msg):
        data = msg.unpickle()
        if isinstance(data, Exception):
            try:
                raise data
            except Exception:
                LOG.exception('_discard_result')
        else:
            LOG.debug('_discard_result: %r', data)

    def call_async(self, with_context, fn, *args, **kwargs):
        LOG.debug('%r.call_async(%r, %r, *%r, **%r)',
                  self, with_context, fn, args, kwargs)

        if isinstance(fn, types.MethodType) and \
           isinstance(fn.im_self, (type, types.ClassType)):
            klass = fn.im_self.__name__
        else:
            klass = None

        call = (with_context, fn.__module__, klass, fn.__name__, args, kwargs)
        self.send(
            mitogen.core.Message.pickled(
                call,
                handle=mitogen.core.CALL_FUNCTION,
                reply_to=self.router.add_handler(self._discard_result),
            )
        )

    def call_with_deadline(self, deadline, with_context, fn, *args, **kwargs):
        """Invoke `fn([context,] *args, **kwargs)` in the external context.

        If `with_context` is ``True``, pass its
        :py:class:`ExternalContext <mitogen.core.ExternalContext>` instance as
        the first parameter.

        If `deadline` is not ``None``, expire the call after `deadline`
        seconds. If `deadline` is ``None``, the invocation may block
        indefinitely."""
        LOG.debug('%r.call_with_deadline(%r, %r, %r, *%r, **%r)',
                  self, deadline, with_context, fn, args, kwargs)

        if isinstance(fn, types.MethodType) and \
           isinstance(fn.im_self, (type, types.ClassType)):
            klass = fn.im_self.__name__
        else:
            klass = None

        call = (with_context, fn.__module__, klass, fn.__name__, args, kwargs)
        response = self.send_await(
            mitogen.core.Message.pickled(
                call,
                handle=mitogen.core.CALL_FUNCTION
            ),
            deadline
        )

        decoded = response.unpickle()
        if isinstance(decoded, mitogen.core.CallError):
            raise decoded
        return decoded

    def call(self, fn, *args, **kwargs):
        """Invoke `fn(*args, **kwargs)` in the external context."""
        return self.call_with_deadline(None, False, fn, *args, **kwargs)


def _proxy_connect(mitogen, name, context_id, klass, kwargs):
    if not isinstance(mitogen.router, Router):  # TODO
        mitogen.router.__class__ = Router  # TODO
        LOG.debug('_proxy_connect(): constructing ModuleForwarder')
        ModuleForwarder(mitogen.router, mitogen.parent, mitogen.importer)

    context = mitogen.router._connect(
        context_id,
        klass,
        name=name,
        **kwargs
    )
    return context.name


class Router(mitogen.core.Router):
    context_id_counter = itertools.count(1)

    debug = False

    def __init__(self, *args, **kwargs):
        super(Router, self).__init__(*args, **kwargs)
        self.responder = ModuleResponder(self)
        self.log_forwarder = LogForwarder(self)

    def enable_debug(self):
        """
        Cause this context and any descendant child contexts to write debug
        logs to /tmp/mitogen.<pid>.log.
        """
        mitogen.core.enable_debug_logging()
        self.debug = True

    def __enter__(self):
        return self

    def __exit__(self, e_type, e_val, tb):
        self.broker.shutdown()
        self.broker.join()

    def context_by_id(self, context_id):
        return self._context_by_id.get(context_id)

    def local(self, **kwargs):
        return self.connect(Stream, **kwargs)

    def sudo(self, **kwargs):
        import mitogen.sudo
        return self.connect(mitogen.sudo.Stream, **kwargs)

    def ssh(self, **kwargs):
        import mitogen.ssh
        return self.connect(mitogen.ssh.Stream, **kwargs)

    def _connect(self, context_id, klass, name=None, **kwargs):
        context = Context(self, context_id)
        stream = klass(self, context.context_id, context.key, **kwargs)
        if name is not None:
            stream.name = name
        stream.connect()
        context.name = stream.name
        self.register(context, stream)
        return context

    def connect(self, klass, name=None, **kwargs):
        kwargs.setdefault('debug', self.debug)

        via = kwargs.pop('via', None)
        if via is not None:
            return self.proxy_connect(via, klass, name=name, **kwargs)

        context_id = self.context_id_counter.next()
        return self._connect(context_id, klass, name=name, **kwargs)

    def proxy_connect(self, via_context, klass, name=None, **kwargs):
        context_id = self.context_id_counter.next()
        # Must be added prior to _proxy_connect() to avoid a race.
        self.add_route(context_id, via_context.context_id)
        name = via_context.call_with_deadline(None, True,
            _proxy_connect, name, context_id, klass, kwargs
        )
        # name = '%s.%s' % (via_context.name, name)
        context = Context(self, context_id, name=name)
        context.via = via_context

        child = via_context
        parent = via_context.via
        while parent is not None:
            LOG.debug('Adding route to %r for %r via %r', parent, context, child)
            parent.send(
                mitogen.core.Message(
                    data='%s\x00%s' % (context_id, child.context_id),
                    handle=mitogen.core.ADD_ROUTE,
                )
            )
            child = parent
            parent = parent.via

        self._context_by_id[context.context_id] = context
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
