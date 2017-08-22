"""
This module implements functionality required by master processes, such as
starting new contexts via SSH. Its size is also restricted, since it must be
sent to any context that will be used to establish additional child contexts.
"""

import errno
import getpass
import imp
import inspect
import logging
import os
import pkgutil
import re
import select
import socket
import sys
import textwrap
import time
import types
import zlib

if not hasattr(pkgutil, 'find_loader'):
    # find_loader() was new in >=2.5, but the modern pkgutil.py syntax has
    # been kept intentionally 2.3 compatible so we can reuse it.
    from econtext.compat import pkgutil

import econtext.core


LOG = logging.getLogger('econtext')
IOLOG = logging.getLogger('econtext.io')
RLOG = logging.getLogger('econtext.ctx')

DOCSTRING_RE = re.compile(r'""".+?"""', re.M | re.S)
COMMENT_RE = re.compile(r'^[ ]*#[^\n]*$', re.M)
IOLOG_RE = re.compile(r'^[ ]*IOLOG.debug\(.+?\)$', re.M)

PERMITTED_CLASSES = set([
    ('econtext.core', 'CallError'),
    ('econtext.core', 'Dead'),
])


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

    raise econtext.core.TimeoutError('read timed out')


def iter_read(fd, deadline):
    if deadline is not None:
        LOG.error('Warning: iter_read(.., deadline=...) unimplemented')

    bits = []
    while True:
        try:
            s = os.read(fd, 4096)
        except OSError, e:
            IOLOG.debug('iter_read(%r) -> OSError: %s', fd, e)
            # See econtext.core.on_receive() EIO comment.
            if e.errno != errno.EIO:
                raise
            s = ''

        if not s:
            raise econtext.core.StreamError(
                'EOF on stream; last 100 bytes received: %r' %
                (''.join(bits)[-100:],)
            )

        bits.append(s)
        yield s


def discard_until(fd, s, deadline):
    for buf in iter_read(fd, deadline):
        if buf.endswith(s):
            return


class LogForwarder(object):
    _log = None

    def __init__(self, context):
        self._context = context
        context.add_handler(self.forward, econtext.core.FORWARD_LOG)

    def forward(self, msg):
        if not self._log:
            # Delay initialization so Stream has a chance to set Context's
            # default name, if one wasn't otherwise specified.
            name = '%s.%s' % (RLOG.name, self._context.name)
            self._log = logging.getLogger(name)
        if msg != econtext.core._DEAD:
            name, level_s, s = msg.data.split('\x00', 2)
            self._log.log(int(level_s), '%s: %s', name, s)

    def __repr__(self):
        return 'LogForwarder(%r)' % (self._context,)


class ModuleResponder(object):
    def __init__(self, context):
        self._context = context
        context.add_handler(self.get_module, econtext.core.GET_MODULE)

    def __repr__(self):
        return 'ModuleResponder(%r)' % (self._context,)

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

    def get_module(self, msg):
        LOG.debug('%r.get_module(%r)', self, msg)
        if msg == econtext.core._DEAD:
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
            self._context.send(
                econtext.core.Message.pickled(
                    (pkg_present, path, compressed),
                    handle=msg.reply_to
                )
            )
        except Exception:
            LOG.debug('While importing %r', fullname, exc_info=True)
            self._context.send(reply_to, None)


class Message(econtext.core.Message):
    """
    Message subclass that controls unpickling.
    """
    def _find_global(self, module_name, class_name):
        """Return the class implementing `module_name.class_name` or raise
        `StreamError` if the module is not whitelisted."""
        if (module_name, class_name) not in PERMITTED_CLASSES:
            raise econtext.core.StreamError(
                '%r attempted to unpickle %r in module %r',
                self._context, class_name, module_name)
        return getattr(sys.modules[module_name], class_name)


class Stream(econtext.core.Stream):
    """
    Base for streams capable of starting new slaves.
    """
    message_class = Message

    #: The path to the remote Python interpreter.
    python_path = 'python2.7'

    def construct(self, remote_name=None, python_path=None, **kwargs):
        """Get the named context running on the local machine, creating it if
        it does not exist."""
        super(Stream, self).construct(**kwargs)
        if python_path:
            self.python_path = python_path

        if remote_name is None:
            remote_name = '%s@%s:%d'
            remote_name %= (getpass.getuser(), socket.gethostname(), os.getpid())
        self.remote_name = remote_name
        self.name = 'local.default'

    def on_shutdown(self, broker):
        """Request the slave gracefully shut itself down."""
        LOG.debug('%r closing CALL_FUNCTION channel', self)
        self.send(
            econtext.core.Message.pickled(
                econtext.core._DEAD,
                src_id=econtext.context_id,
                dst_id=self.remote_id,
                handle=econtext.core.CALL_FUNCTION
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
            os.execv(sys.executable,['econtext:CONTEXT_NAME'])
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
        source = inspect.getsource(econtext.core)
        source += '\nExternalContext().main%r\n' % ((
            # econtext.context_id,       # parent_id
            0,
            self.remote_id,            # context_id
            self.key,
            LOG.level or logging.getLogger().level or logging.INFO,
        ),)

        compressed = zlib.compress(minimize_source(source))
        return str(len(compressed)) + '\n' + compressed

    create_child = staticmethod(create_child)

    def connect(self):
        LOG.debug('%r.connect()', self)
        pid, fd = self.create_child(*self.get_boot_command())
        self.receive_side = econtext.core.Side(self, fd)
        self.transmit_side = econtext.core.Side(self, os.dup(fd))
        LOG.debug('%r.connect(): child process stdin/stdout=%r',
                  self, self.receive_side.fd)

        self._connect_bootstrap()

    def _ec0_received(self):
        LOG.debug('%r._ec0_received()', self)
        write_all(self.transmit_side.fd, self.get_preamble())
        discard_until(self.receive_side.fd, 'EC1\n', time.time() + 10.0)

    def _connect_bootstrap(self):
        discard_until(self.receive_side.fd, 'EC0\n', time.time() + 10.0)
        return self._ec0_received()


class Broker(econtext.core.Broker):
    shutdown_timeout = 5.0


class Context(econtext.core.Context):
    via = None

    def __init__(self, *args, **kwargs):
        super(Context, self).__init__(*args, **kwargs)
        self.responder = ModuleResponder(self)
        self.log_forwarder = LogForwarder(self)

    def on_disconnect(self, broker):
        pass

    def call_with_deadline(self, deadline, with_context, fn, *args, **kwargs):
        """Invoke `fn([context,] *args, **kwargs)` in the external context.

        If `with_context` is ``True``, pass its
        :py:class:`ExternalContext <econtext.core.ExternalContext>` instance as
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
            econtext.core.Message.pickled(
                call,
                handle=econtext.core.CALL_FUNCTION
            ),
            deadline
        )

        decoded = response.unpickle()
        if isinstance(decoded, econtext.core.CallError):
            raise decoded
        return decoded

    def call(self, fn, *args, **kwargs):
        """Invoke `fn(*args, **kwargs)` in the external context."""
        return self.call_with_deadline(None, False, fn, *args, **kwargs)


def _proxy_connect(econtext, name, context_id, klass, kwargs):
    econtext.router.__class__ = Router  # TODO
    context = econtext.router._connect(
        context_id,
        klass,
        name=name,
        **kwargs
    )
    return context.name


class Router(econtext.core.Router):
    next_slave_id = 10

    def alloc_slave_id(self):
        """Allocate a context_id for a slave about to be created."""
        self.next_slave_id += 1
        return self.next_slave_id

    def __enter__(self):
        return self

    def __exit__(self, e_type, e_val, tb):
        self.broker.shutdown()
        self.broker.join()

    def _connect(self, context_id, klass, name=None, **kwargs):
        context = Context(self, context_id)
        stream = klass(self, context.context_id, context.key, **kwargs)
        context.name = name or stream.name
        stream.connect()
        self.register(context, stream)
        return context

    def connect(self, klass, name=None, **kwargs):
        context_id = self.alloc_slave_id()
        return self._connect(context_id, klass, name=name, **kwargs)

    def proxy_connect(self, via_context, klass, name=None, **kwargs):
        context_id = self.alloc_slave_id()
        name = via_context.call_with_deadline(3.0, True,
            _proxy_connect, name, context_id, klass, kwargs
        )
        name = '%s.%s' % (via_context.name, name)
        context = Context(self, context_id, name=name)
        context.via = via_context

        child = via_context
        parent = via_context.via
        while parent is not None:
            LOG.info('Adding route to %r for %r via %r', parent, context, child)
            parent.send(
                econtext.core.Message(
                    data='%s\x00%s' % (context_id, child.context_id),
                    handle=econtext.core.ADD_ROUTE,
                )
            )

        self.add_route(context_id, via_context.context_id)
        self._context_by_id[context.context_id] = context
        return context
