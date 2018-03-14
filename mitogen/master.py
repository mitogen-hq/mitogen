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

import dis
import imp
import inspect
import itertools
import logging
import os
import pkgutil
import re
import sys
import threading
import types
import zlib

if not hasattr(pkgutil, 'find_loader'):
    # find_loader() was new in >=2.5, but the modern pkgutil.py syntax has
    # been kept intentionally 2.3 compatible so we can reuse it.
    from mitogen.compat import pkgutil

import mitogen.core
import mitogen.parent
from mitogen.core import LOG


RLOG = logging.getLogger('mitogen.ctx')


def _stdlib_paths():
    """Return a set of paths from which Python imports the standard library.
    """
    attr_candidates = [
        'prefix',
        'real_prefix',  # virtualenv: only set inside a virtual environment.
        'base_prefix',  # venv: always set, equal to prefix if outside.
    ]
    prefixes = (getattr(sys, a) for a in attr_candidates if hasattr(sys, a))
    version = 'python%s.%s' % sys.version_info[0:2]
    return set(os.path.abspath(os.path.join(p, 'lib', version))
               for p in prefixes)


def get_child_modules(path):
    it = pkgutil.iter_modules([os.path.dirname(path)])
    return [name for _, name, _ in it]


LOAD_CONST = dis.opname.index('LOAD_CONST')
IMPORT_NAME = dis.opname.index('IMPORT_NAME')


def scan_code_imports(co):
    """Given a code object `co`, scan its bytecode yielding any
    ``IMPORT_NAME`` and associated prior ``LOAD_CONST`` instructions
    representing an `Import` statement or `ImportFrom` statement.

    :return:
        Generator producing `(level, modname, namelist)` tuples, where:

        * `level`: -1 for normal import, 0, for absolute import, and >0 for
          relative import.
        * `modname`: Name of module to import, or from where `namelist` names
          are imported.
        * `namelist`: for `ImportFrom`, the list of names to be imported from
          `modname`.
    """
    # Yield `(op, oparg)` tuples from the code object `co`.
    ordit = itertools.imap(ord, co.co_code)
    nextb = ordit.next

    opit = ((c, (None
                 if c < dis.HAVE_ARGUMENT else
                 (nextb() | (nextb() << 8))))
            for c in ordit)

    opit, opit2, opit3 = itertools.tee(opit, 3)
    try:
        next(opit2)
        next(opit3)
        next(opit3)
    except StopIteration:
        return

    for oparg1, oparg2, (op3, arg3) in itertools.izip(opit, opit2, opit3):
        if op3 == IMPORT_NAME:
            op2, arg2 = oparg2
            op1, arg1 = oparg1
            if op1 == op2 == LOAD_CONST:
                yield (co.co_consts[arg1],
                       co.co_names[arg3],
                       co.co_consts[arg2] or ())


_join_lock = threading.Lock()
_join_process_id = None
_join_callbacks_by_target = {}
_join_thread_by_target = {}


def _join_thread_reset():
    """If we have forked since the watch dictionaries were initialized, all
    that has is garbage, so clear it."""
    global _join_process_id

    if os.getpid() != _join_process_id:
        _join_process_id = os.getpid()
        _join_callbacks_by_target.clear()
        _join_thread_by_target.clear()


def join_thread_async(target_thread, on_join):
    """Start a thread that waits for another thread to shutdown, before
    invoking `on_join()`. In CPython it seems possible to use this method to
    ensure a non-main thread is signalled when the main thread has exitted,
    using yet another thread as a proxy."""

    def _watch():
        target_thread.join()
        for on_join in _join_callbacks_by_target[target_thread]:
            on_join()

    _join_lock.acquire()
    try:
        _join_thread_reset()
        _join_callbacks_by_target.setdefault(target_thread, []).append(on_join)
        if target_thread not in _join_thread_by_target:
            _join_thread_by_target[target_thread] = threading.Thread(
                name='mitogen.master.join_thread_async',
                target=_watch,
            )
            _join_thread_by_target[target_thread].start()
    finally:
        _join_lock.release()


class SelectError(mitogen.core.Error):
    pass


class Select(object):
    notify = None

    @classmethod
    def all(cls, receivers):
        return list(msg.unpickle() for msg in cls(receivers))

    def __init__(self, receivers=(), oneshot=True):
        self._receivers = []
        self._oneshot = oneshot
        self._latch = mitogen.core.Latch()
        for recv in receivers:
            self.add(recv)

    def _put(self, value):
        self._latch.put(value)
        if self.notify:
            self.notify(self)

    def __bool__(self):
        return bool(self._receivers)

    def __enter__(self):
        return self

    def __exit__(self, e_type, e_val, e_tb):
        self.close()

    def __iter__(self):
        while self._receivers:
            yield self.get()

    loop_msg = 'Adding this Select instance would create a Select cycle'

    def _check_no_loop(self, recv):
        if recv is self:
            raise SelectError(self.loop_msg)

        for recv_ in self._receivers:
            if recv_ == recv:
                raise SelectError(self.loop_msg)
            if isinstance(recv_, Select):
                recv_._check_no_loop(recv)

    owned_msg = 'Cannot add: Receiver is already owned by another Select'

    def add(self, recv):
        if isinstance(recv, Select):
            recv._check_no_loop(self)

        self._receivers.append(recv)
        if recv.notify is not None:
            raise SelectError(self.owned_msg)

        recv.notify = self._put
        # Avoid race by polling once after installation.
        if not recv.empty():
            self._put(recv)

    not_present_msg = 'Instance is not a member of this Select'

    def remove(self, recv):
        try:
            if recv.notify != self._put:
                raise ValueError
            self._receivers.remove(recv)
            recv.notify = None
        except (IndexError, ValueError):
            raise SelectError(self.not_present_msg)

    def close(self):
        for recv in self._receivers[:]:
            self.remove(recv)

    def empty(self):
        return self._latch.empty()

    empty_msg = 'Cannot get(), Select instance is empty'

    def get(self, timeout=None):
        if not self._receivers:
            raise SelectError(self.empty_msg)

        while True:
            recv = self._latch.get(timeout=timeout)
            try:
                msg = recv.get(block=False)
                if self._oneshot:
                    self.remove(recv)
                msg.receiver = recv
                return msg
            except mitogen.core.TimeoutError:
                # A receiver may have been queued with no result if another
                # thread drained it before we woke up, or because another
                # thread drained it between add() calling recv.empty() and
                # self._put(). In this case just sleep again.
                continue


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


class ModuleFinder(object):
    _STDLIB_PATHS = _stdlib_paths()

    def __init__(self):
        #: Import machinery is expensive, keep :py:meth`:get_module_source`
        #: results around.
        self._found_cache = {}

        #: Avoid repeated dependency scanning, which is expensive.
        self._related_cache = {}

    def __repr__(self):
        return 'ModuleFinder()'

    def is_stdlib_name(self, modname):
        """Return ``True`` if `modname` appears to come from the standard
        library."""
        if imp.is_builtin(modname) != 0:
            return True

        module = sys.modules.get(modname)
        if module is None:
            return False

        # six installs crap with no __file__
        modpath = os.path.abspath(getattr(module, '__file__', ''))
        if 'site-packages' in modpath:
            return False

        for dirname in self._STDLIB_PATHS:
            if os.path.commonprefix((dirname, modpath)) == dirname:
                return True

        return False

    def _py_filename(self, path):
        path = path.rstrip('co')
        if path.endswith('.py'):
            return path

    def _get_module_via_pkgutil(self, fullname):
        """Attempt to fetch source code via pkgutil. In an ideal world, this
        would be the only required implementation of get_module()."""
        loader = pkgutil.find_loader(fullname)
        LOG.debug('pkgutil._get_module_via_pkgutil(%r) -> %r',
                  fullname, loader)
        if not loader:
            return

        try:
            path = self._py_filename(loader.get_filename(fullname))
            source = loader.get_source(fullname)
            is_pkg = loader.is_package(fullname)
        except AttributeError:
            return

        if path is not None and source is not None:
            return path, source, is_pkg

    def _get_module_via_sys_modules(self, fullname):
        """Attempt to fetch source code via sys.modules. This is specifically
        to support __main__, but it may catch a few more cases."""
        module = sys.modules.get(fullname)
        if not isinstance(module, types.ModuleType):
            LOG.debug('sys.modules[%r] absent or not a regular module',
                      fullname)
            return

        path = self._py_filename(getattr(module, '__file__', ''))
        if not path:
            return

        is_pkg = hasattr(module, '__path__')
        try:
            source = inspect.getsource(module)
        except IOError:
            # Work around inspect.getsourcelines() bug for 0-byte __init__.py
            # files.
            if not is_pkg:
                raise
            source = '\n'

        return path, source, is_pkg

    get_module_methods = [_get_module_via_pkgutil,
                          _get_module_via_sys_modules]

    def get_module_source(self, fullname):
        """Given the name of a loaded module `fullname`, attempt to find its
        source code.

        :returns:
            Tuple of `(module path, source text, is package?)`, or ``None`` if
            the source cannot be found.
        """
        tup = self._found_cache.get(fullname)
        if tup:
            return tup

        for method in self.get_module_methods:
            tup = method(self, fullname)
            if tup:
                break
        else:
            tup = None, None, None
            LOG.debug('get_module_source(%r): cannot find source', fullname)

        self._found_cache[fullname] = tup
        return tup

    def resolve_relpath(self, fullname, level):
        """Given an ImportFrom AST node, guess the prefix that should be tacked
        on to an alias name to produce a canonical name. `fullname` is the name
        of the module in which the ImportFrom appears."""
        mod = sys.modules.get(fullname, None)
        if hasattr(mod, '__path__'):
            fullname += '.__init__'

        if level == 0 or not fullname:
            return ''

        bits = fullname.split('.')
        if len(bits) <= level:
            # This would be an ImportError in real code.
            return ''

        return '.'.join(bits[:-level])

    def generate_parent_names(self, fullname):
        while '.' in fullname:
            fullname, _, _ = fullname.rpartition('.')
            yield fullname

    def find_related_imports(self, fullname):
        """
        Return a list of non-stdlb modules that are directly imported by
        `fullname`, plus their parents.

        The list is determined by retrieving the source code of
        `fullname`, compiling it, and examining all IMPORT_NAME ops.

        :param fullname: Fully qualified name of an _already imported_ module
            for which source code can be retrieved
        :type fullname: str
        """
        related = self._related_cache.get(fullname)
        if related is not None:
            return related

        modpath, src, _ = self.get_module_source(fullname)
        if src is None:
            return []

        maybe_names = list(self.generate_parent_names(fullname))

        co = compile(src, modpath, 'exec')
        for level, modname, namelist in scan_code_imports(co):
            if level == -1:
                modnames = [modname, '%s.%s' % (fullname, modname)]
            else:
                modnames = [
                    '%s.%s' % (self.resolve_relpath(fullname, level), modname)
                ]

            maybe_names.extend(modnames)
            maybe_names.extend(
                '%s.%s' % (mname, name)
                for mname in modnames
                for name in namelist
            )

        return self._related_cache.setdefault(fullname, sorted(
            set(
                name
                for name in maybe_names
                if sys.modules.get(name) is not None
                and not self.is_stdlib_name(name)
                and 'six.moves' not in name  # TODO: crap
            )
        ))

    def find_related(self, fullname):
        """
        Return a list of non-stdlib modules that are imported directly or
        indirectly by `fullname`, plus their parents.

        This method is like :py:meth:`on_disconect`, but it also recursively
        searches any modules which are imported by `fullname`.

        :param fullname: Fully qualified name of an _already imported_ module
            for which source code can be retrieved
        :type fullname: str
        """
        stack = [fullname]
        found = set()

        while stack:
            name = stack.pop(0)
            names = self.find_related_imports(name)
            stack.extend(set(names).difference(found, stack))
            found.update(names)

        found.discard(fullname)
        return sorted(found)


class ModuleResponder(object):
    def __init__(self, router):
        self._router = router
        self._finder = ModuleFinder()
        self._cache = {}  # fullname -> pickled
        self.blacklist = []
        self.whitelist = ['']
        router.add_handler(self._on_get_module, mitogen.core.GET_MODULE)

    def __repr__(self):
        return 'ModuleResponder(%r)' % (self._router,)

    MAIN_RE = re.compile(r'^if\s+__name__\s*==\s*.__main__.\s*:', re.M)

    def whitelist_prefix(self, fullname):
        if self.whitelist == ['']:
            self.whitelist = ['mitogen']
        self.whitelist.append(fullname)

    def blacklist_prefix(self, fullname):
        self.blacklist.append(fullname)

    def neutralize_main(self, src):
        """Given the source for the __main__ module, try to find where it
        begins conditional execution based on a "if __name__ == '__main__'"
        guard, and remove any code after that point."""
        match = self.MAIN_RE.search(src)
        if match:
            return src[:match.start()]
        return src

    def _build_tuple(self, fullname):
        if mitogen.core.is_blacklisted_import(self, fullname):
            raise ImportError('blacklisted')

        if fullname in self._cache:
            return self._cache[fullname]

        path, source, is_pkg = self._finder.get_module_source(fullname)
        if source is None:
            LOG.error('_build_tuple(%r): could not locate source', fullname)
            tup = fullname, None, None, None, ()
            self._cache[fullname] = tup
            return tup

        if source is None:
            raise ImportError('could not find %r' % (fullname,))

        if is_pkg:
            pkg_present = get_child_modules(path)
            LOG.debug('_build_tuple(%r, %r) -> %r',
                      path, fullname, pkg_present)
        else:
            pkg_present = None

        if fullname == '__main__':
            source = self.neutralize_main(source)
        compressed = zlib.compress(source, 9)
        related = [
            name
            for name in self._finder.find_related(fullname)
            if not mitogen.core.is_blacklisted_import(self, name)
        ]
        # 0:fullname 1:pkg_present 2:path 3:compressed 4:related
        tup = fullname, pkg_present, path, compressed, related
        self._cache[fullname] = tup
        return tup

    def _send_load_module(self, stream, msg, fullname):
        LOG.debug('_send_load_module(%r, %r)', stream, fullname)
        msg.reply(self._build_tuple(fullname),
                  handle=mitogen.core.LOAD_MODULE)
        stream.sent_modules.add(fullname)

    def _on_get_module(self, msg):
        if msg == mitogen.core._DEAD:
            return

        LOG.debug('%r._on_get_module(%r)', self, msg.data)
        stream = self._router.stream_by_id(msg.src_id)
        fullname = msg.data
        if fullname in stream.sent_modules:
            LOG.warning('_on_get_module(): dup request for %r from %r',
                        fullname, stream)

        try:
            tup = self._build_tuple(fullname)
            for name in tup[4]:  # related
                parent, _, _ = name.partition('.')
                if parent != fullname and parent not in stream.sent_modules:
                    # Parent hasn't been sent, so don't load submodule yet.
                    continue

                if name in stream.sent_modules:
                    # Submodule has been sent already, skip.
                    continue

                self._send_load_module(stream, msg, name)
            self._send_load_module(stream, msg, fullname)

        except Exception:
            LOG.debug('While importing %r', fullname, exc_info=True)
            msg.reply((fullname, None, None, None, []),
                      handle=mitogen.core.LOAD_MODULE)


class Broker(mitogen.core.Broker):
    shutdown_timeout = 5.0

    def __init__(self, install_watcher=True):
        if install_watcher:
            join_thread_async(threading.currentThread(), self.shutdown)
        super(Broker, self).__init__()


class Context(mitogen.core.Context):
    via = None

    def on_disconnect(self, broker):
        """
        Override base behaviour of triggering Broker shutdown on parent stream
        disconnection.
        """
        mitogen.core.fire(self, 'disconnect')

    def call_async(self, fn, *args, **kwargs):
        LOG.debug('%r.call_async(%r, *%r, **%r)',
                  self, fn, args, kwargs)

        if isinstance(fn, types.MethodType) and \
           isinstance(fn.im_self, (type, types.ClassType)):
            klass = fn.im_self.__name__
        else:
            klass = None

        return self.send_async(
            mitogen.core.Message.pickled(
                (fn.__module__, klass, fn.__name__, args, kwargs),
                handle=mitogen.core.CALL_FUNCTION,
            )
        )

    def call(self, fn, *args, **kwargs):
        receiver = self.call_async(fn, *args, **kwargs)
        return receiver.get().unpickle(throw_dead=False)


class Router(mitogen.parent.Router):
    context_class = Context
    broker_class = Broker
    debug = False
    profiling = False

    def __init__(self, broker=None):
        if broker is None:
            broker = self.broker_class()
        super(Router, self).__init__(broker)
        self.id_allocator = IdAllocator(self)
        self.responder = ModuleResponder(self)
        self.log_forwarder = LogForwarder(self)

    def enable_debug(self):
        mitogen.core.enable_debug_logging()
        self.debug = True

    def __enter__(self):
        return self

    def __exit__(self, e_type, e_val, tb):
        self.broker.shutdown()
        self.broker.join()

    def docker(self, **kwargs):
        return self.connect('docker', **kwargs)

    def local(self, **kwargs):
        return self.connect('local', **kwargs)

    def sudo(self, **kwargs):
        return self.connect('sudo', **kwargs)

    def ssh(self, **kwargs):
        return self.connect('ssh', **kwargs)

    def propagate_route(self, target, via):
        self.add_route(target.context_id, via.context_id)
        child = via
        parent = via.via

        while parent is not None:
            LOG.debug('Adding route to %r for %r via %r',
                      parent, target, child)
            parent.send(
                mitogen.core.Message(
                    data='%s\x00%s' % (target.context_id, child.context_id),
                    handle=mitogen.core.ADD_ROUTE,
                )
            )
            child = parent
            parent = parent.via

    def disconnect_stream(self, stream):
        self.broker.defer(stream.on_disconnect, self.broker)

    def disconnect_all(self):
        for stream in self._stream_by_id.values():
            self.disconnect_stream(stream)


class IdAllocator(object):
    def __init__(self, router):
        self.router = router
        self.next_id = 1
        self.lock = threading.Lock()
        router.add_handler(self.on_allocate_id, mitogen.core.ALLOCATE_ID)

    def __repr__(self):
        return 'IdAllocator(%r)' % (self.router,)

    def allocate(self):
        self.lock.acquire()
        try:
            id_ = self.next_id
            self.next_id += 1
            return id_
        finally:
            self.lock.release()

    def on_allocate_id(self, msg):
        if msg == mitogen.core._DEAD:
            return

        id_ = self.allocate()
        requestee = self.router.context_by_id(msg.src_id)
        allocated = self.router.context_by_id(id_, msg.src_id)

        LOG.debug('%r: allocating %r to %r', self, allocated, requestee)
        msg.reply(id_)

        LOG.debug('%r: publishing route to %r via %r', self,
                  allocated, requestee)
        self.router.propagate_route(allocated, requestee)
