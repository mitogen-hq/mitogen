"""
This module implements functionality required by master processes, such as
starting new contexts via SSH. Its size is also restricted, since it must be
sent to any context that will be used to establish additional child contexts.
"""

import getpass
import imp
import inspect
import logging
import os
import pkgutil
import re
import socket
import sys
import textwrap
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


class LogForwarder(object):
    def __init__(self, context):
        self._context = context
        self._context.add_handle_cb(self.forward_log,
                                    handle=econtext.core.FORWARD_LOG)
        name = '%s.%s' % (RLOG.name, self._context.name)
        self._log = logging.getLogger(name)

    def forward_log(self, data):
        if data == econtext.core._DEAD:
            return

        name, level, s = data
        self._log.log(level, '%s: %s', name, s)


class ModuleResponder(object):
    def __init__(self, context):
        self._context = context
        self._context.add_handle_cb(self.get_module,
                                    handle=econtext.core.GET_MODULE)

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

    def get_module(self, data):
        LOG.debug('%r.get_module(%r)', self, data)
        if data == econtext.core._DEAD:
            return

        reply_to, fullname = data
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
            reply = (pkg_present, path, compressed)
            self._context.enqueue(reply_to, reply)
        except Exception:
            LOG.debug('While importing %r', fullname, exc_info=True)
            self._context.enqueue(reply_to, None)


class Stream(econtext.core.Stream):
    """
    Base for streams capable of starting new slaves.
    """
    #: The path to the remote Python interpreter.
    python_path = sys.executable

    def __init__(self, context):
        super(Stream, self).__init__(context)
        self._permitted_classes = set([
            ('econtext.core', 'CallError'),
            ('econtext.core', 'Dead'),
        ])

    def on_shutdown(self, broker):
        """Request the slave gracefully shut itself down."""
        LOG.debug('%r closing CALL_FUNCTION channel', self)
        self.enqueue(econtext.core.CALL_FUNCTION, econtext.core._DEAD)

    def _find_global(self, module_name, class_name):
        """Return the class implementing `module_name.class_name` or raise
        `StreamError` if the module is not whitelisted."""
        if (module_name, class_name) not in self._permitted_classes:
            raise econtext.core.StreamError(
                '%r attempted to unpickle %r in module %r',
                self._context, class_name, module_name)
        return getattr(sys.modules[module_name], class_name)

    def allow_class(self, module_name, class_name):
        """Add `module_name` to the list of permitted modules."""
        self._permitted_modules.add((module_name, class_name))

    # base64'd and passed to 'python -c'. It forks, dups 0->100, creates a
    # pipe, then execs a new interpreter with a custom argv. 'CONTEXT_NAME' is
    # replaced with the context name. Optimized for size.
    def _first_stage():
        import os,sys,zlib
        R,W=os.pipe()
        if os.fork():
            os.dup2(0,100)
            os.dup2(R,0)
            os.close(R)
            os.close(W)
            os.execv(sys.executable,['econtext:CONTEXT_NAME'])
        else:
            os.fdopen(W,'wb',0).write(zlib.decompress(sys.stdin.read(input())))
            print('OK')
            sys.exit(0)

    def get_boot_command(self):
        name = self._context.remote_name
        if name is None:
            name = '%s@%s:%d'
            name %= (getpass.getuser(), socket.gethostname(), os.getpid())

        source = inspect.getsource(self._first_stage)
        source = textwrap.dedent('\n'.join(source.strip().split('\n')[1:]))
        source = source.replace('    ', '\t')
        source = source.replace('CONTEXT_NAME', name)
        encoded = source.encode('base64').replace('\n', '')
        return [self.python_path, '-c',
                'exec("%s".decode("base64"))' % (encoded,)]

    def __repr__(self):
        return '%s(%s)' % (self.__class__.__name__, self._context)

    def get_preamble(self):
        source = inspect.getsource(econtext.core)
        source += '\nExternalContext().main%r\n' % ((
            self._context.key,
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

        econtext.core.write_all(self.transmit_side.fd, self.get_preamble())
        s = os.read(self.receive_side.fd, 4096)
        if s != 'OK\n':
            raise econtext.core.StreamError('Bootstrap failed; stdout: %r', s)


class Broker(econtext.core.Broker):
    shutdown_timeout = 5.0


class Context(econtext.core.Context):
    def __init__(self, *args, **kwargs):
        super(Context, self).__init__(*args, **kwargs)
        self.responder = ModuleResponder(self)
        self.log_forwarder = LogForwarder(self)

    def on_disconnect(self, broker):
        self.stream = None

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
        result = self.enqueue_await_reply(econtext.core.CALL_FUNCTION,
                                          deadline, call)
        if isinstance(result, econtext.core.CallError):
            raise result
        return result

    def call(self, fn, *args, **kwargs):
        """Invoke `fn(*args, **kwargs)` in the external context."""
        return self.call_with_deadline(None, False, fn, *args, **kwargs)


def connect(broker, name='default', python_path=None):
    """Get the named context running on the local machine, creating it if
    it does not exist."""
    context = Context(broker, name)
    context.stream = Stream(context)
    if python_path:
        context.stream.python_path = python_path
    context.stream.connect()
    return broker.register(context)
