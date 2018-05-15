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

import collections
import errno
import fcntl
import imp
import itertools
import logging
import os
import select
import signal
import socket
import struct
import sys
import threading
import time
import traceback
import warnings
import weakref
import zlib

try:
    import cPickle
except ImportError:
    import pickle as cPickle

try:
    from cStringIO import StringIO as BytesIO
except ImportError:
    from io import BytesIO

# TODO: usage of 'import' after setting __name__, but before fixing up
# sys.modules generates a warning. This happens when profiling = True.
warnings.filterwarnings('ignore',
    "Parent module 'mitogen' not found while handling absolute import")

LOG = logging.getLogger('mitogen')
IOLOG = logging.getLogger('mitogen.io')
IOLOG.setLevel(logging.INFO)

_v = False
_vv = False

GET_MODULE = 100
CALL_FUNCTION = 101
FORWARD_LOG = 102
ADD_ROUTE = 103
DEL_ROUTE = 104
ALLOCATE_ID = 105
SHUTDOWN = 106
LOAD_MODULE = 107
FORWARD_MODULE = 108
DETACHING = 109
IS_DEAD = 999

try:
    BaseException
except NameError:
    BaseException = Exception

PY3 = sys.version_info > (3,)
if PY3:
    b = lambda s: s.encode('latin-1')
    BytesType = bytes
    UnicodeType = unicode
else:
    b = str
    BytesType = str
    UnicodeType = unicode

CHUNK_SIZE = 131072
_tls = threading.local()


if __name__ == 'mitogen.core':
    # When loaded using import mechanism, ExternalContext.main() will not have
    # a chance to set the synthetic mitogen global, so just import it here.
    import mitogen
else:
    # When loaded as __main__, ensure classes and functions gain a __module__
    # attribute consistent with the host process, so that pickling succeeds.
    __name__ = 'mitogen.core'


class Error(Exception):
    def __init__(self, fmt=None, *args):
        if args:
            fmt %= args
        Exception.__init__(self, fmt)


class LatchError(Error):
    pass


class Blob(BytesType):
    def __repr__(self):
        return '[blob: %d bytes]' % len(self)

    def __reduce__(self):
        return (Blob, (BytesType(self),))


class Secret(UnicodeType):
    def __repr__(self):
        return '[secret]'

    def __str__(self):
        return UnicodeType(self)

    def __reduce__(self):
        return (Secret, (UnicodeType(self),))


class CallError(Error):
    def __init__(self, fmt=None, *args):
        if not isinstance(fmt, BaseException):
            Error.__init__(self, fmt, *args)
        else:
            e = fmt
            fmt = '%s.%s: %s' % (type(e).__module__, type(e).__name__, e)
            args = ()
            tb = sys.exc_info()[2]
            if tb:
                fmt += '\n'
                fmt += ''.join(traceback.format_tb(tb))
            Error.__init__(self, fmt)

    def __reduce__(self):
        return (_unpickle_call_error, (self[0],))


def _unpickle_call_error(s):
    if not (type(s) is str and len(s) < 10000):
        raise TypeError('cannot unpickle CallError: bad input')
    inst = CallError.__new__(CallError)
    Exception.__init__(inst, s)
    return inst


class ChannelError(Error):
    remote_msg = 'Channel closed by remote end.'
    local_msg = 'Channel closed by local end.'


class StreamError(Error):
    pass


class TimeoutError(Error):
    pass


def has_parent_authority(msg, _stream=None):
    return (msg.auth_id == mitogen.context_id or
            msg.auth_id in mitogen.parent_ids)


def listen(obj, name, func):
    signals = vars(obj).setdefault('_signals', {})
    signals.setdefault(name, []).append(func)


def fire(obj, name, *args, **kwargs):
    signals = vars(obj).get('_signals', {})
    return [func(*args, **kwargs) for func in signals.get(name, ())]


def takes_econtext(func):
    func.mitogen_takes_econtext = True
    return func


def takes_router(func):
    func.mitogen_takes_router = True
    return func


def is_blacklisted_import(importer, fullname):
    """Return ``True`` if `fullname` is part of a blacklisted package, or if
    any packages have been whitelisted and `fullname` is not part of one.

    NB:
      - If a package is on both lists, then it is treated as blacklisted.
      - If any package is whitelisted, then all non-whitelisted packages are
        treated as blacklisted.
    """
    return ((not any(fullname.startswith(s) for s in importer.whitelist)) or
                (any(fullname.startswith(s) for s in importer.blacklist)))


def set_cloexec(fd):
    flags = fcntl.fcntl(fd, fcntl.F_GETFD)
    assert fd > 2
    fcntl.fcntl(fd, fcntl.F_SETFD, flags | fcntl.FD_CLOEXEC)


def set_nonblock(fd):
    flags = fcntl.fcntl(fd, fcntl.F_GETFL)
    fcntl.fcntl(fd, fcntl.F_SETFL, flags | os.O_NONBLOCK)


def set_block(fd):
    flags = fcntl.fcntl(fd, fcntl.F_GETFL)
    fcntl.fcntl(fd, fcntl.F_SETFL, flags & ~os.O_NONBLOCK)


def io_op(func, *args):
    while True:
        try:
            return func(*args), False
        except (select.error, OSError, IOError):
            e = sys.exc_info()[1]
            _vv and IOLOG.debug('io_op(%r) -> OSError: %s', func, e)
            if e[0] == errno.EINTR:
                continue
            if e[0] in (errno.EIO, errno.ECONNRESET, errno.EPIPE):
                return None, True
            raise


class PidfulStreamHandler(logging.StreamHandler):
    open_pid = None
    template = '/tmp/mitogen.%s.%s.log'

    def _reopen(self):
        self.acquire()
        try:
            if self.open_pid == os.getpid():
                return
            ts = time.strftime('%Y%m%d_%H%M%S')
            path = self.template % (os.getpid(), ts)
            self.stream = open(path, 'w', 1)
            set_cloexec(self.stream.fileno())
            self.stream.write('Parent PID: %s\n' % (os.getppid(),))
            self.stream.write('Created by:\n\n%s\n' % (
                ''.join(traceback.format_stack()),
            ))
            self.open_pid = os.getpid()
        finally:
            self.release()

    def emit(self, record):
        if self.open_pid != os.getpid():
            self._reopen()
        return super(PidfulStreamHandler, self).emit(record)


def enable_debug_logging():
    global _v, _vv
    _v = True
    _vv = True
    root = logging.getLogger()
    root.setLevel(logging.DEBUG)
    IOLOG.setLevel(logging.DEBUG)
    handler = PidfulStreamHandler()
    handler.formatter = logging.Formatter(
        '%(asctime)s %(levelname).1s %(name)s: %(message)s',
        '%H:%M:%S'
    )
    root.handlers.insert(0, handler)


_profile_hook = lambda name, func, *args: func(*args)

def enable_profiling():
    global _profile_hook
    import cProfile, pstats
    def _profile_hook(name, func, *args):
        profiler = cProfile.Profile()
        profiler.enable()
        try:
            return func(*args)
        finally:
            profiler.create_stats()
            fp = open('/tmp/mitogen.stats.%d.%s.log' % (os.getpid(), name), 'w')
            try:
                stats = pstats.Stats(profiler, stream=fp)
                stats.sort_stats('cumulative')
                stats.print_stats()
            finally:
                fp.close()


class Message(object):
    dst_id = None
    src_id = None
    auth_id = None
    handle = None
    reply_to = None
    data = ''
    _unpickled = object()

    router = None
    receiver = None

    def __init__(self, **kwargs):
        self.src_id = mitogen.context_id
        self.auth_id = mitogen.context_id
        vars(self).update(kwargs)
        assert isinstance(self.data, str)

    def _unpickle_context(self, context_id, name):
        return _unpickle_context(self.router, context_id, name)

    def _unpickle_sender(self, context_id, dst_handle):
        return _unpickle_sender(self.router, context_id, dst_handle)

    def _find_global(self, module, func):
        """Return the class implementing `module_name.class_name` or raise
        `StreamError` if the module is not whitelisted."""
        if module == __name__:
            if func == '_unpickle_call_error':
                return _unpickle_call_error
            elif func == '_unpickle_sender':
                return self._unpickle_sender
            elif func == '_unpickle_context':
                return self._unpickle_context
            elif func == 'Blob':
                return Blob
            elif func == 'Secret':
                return Secret
        raise StreamError('cannot unpickle %r/%r', module, func)

    @property
    def is_dead(self):
        return self.reply_to == IS_DEAD

    @classmethod
    def dead(cls, **kwargs):
        return cls(reply_to=IS_DEAD, **kwargs)

    @classmethod
    def pickled(cls, obj, **kwargs):
        self = cls(**kwargs)
        try:
            self.data = cPickle.dumps(obj, protocol=2)
        except cPickle.PicklingError:
            e = sys.exc_info()[1]
            self.data = cPickle.dumps(CallError(e), protocol=2)
        return self

    def reply(self, msg, router=None, **kwargs):
        if not isinstance(msg, Message):
            msg = Message.pickled(msg)
        msg.dst_id = self.src_id
        msg.handle = self.reply_to
        vars(msg).update(kwargs)
        (self.router or router).route(msg)

    def unpickle(self, throw=True, throw_dead=True):
        """Deserialize `data` into an object."""
        _vv and IOLOG.debug('%r.unpickle()', self)
        if throw_dead and self.is_dead:
            raise ChannelError(ChannelError.remote_msg)

        obj = self._unpickled
        if obj is Message._unpickled:
            fp = BytesIO(self.data)
            unpickler = cPickle.Unpickler(fp)
            try:
                unpickler.find_global = self._find_global
            except AttributeError:
                unpickler.find_class = self._find_global

            try:
                # Must occur off the broker thread.
                obj = unpickler.load()
                self._unpickled = obj
            except (TypeError, ValueError):
                e = sys.exc_info()[1]
                raise StreamError('invalid message: %s', e)

        if throw:
            if isinstance(obj, CallError):
                raise obj

        return obj

    def __repr__(self):
        return 'Message(%r, %r, %r, %r, %r, %r..%d)' % (
            self.dst_id, self.src_id, self.auth_id, self.handle,
            self.reply_to, (self.data or '')[:50], len(self.data)
        )


class Sender(object):
    def __init__(self, context, dst_handle):
        self.context = context
        self.dst_handle = dst_handle

    def __repr__(self):
        return 'Sender(%r, %r)' % (self.context, self.dst_handle)

    def __reduce__(self):
        return _unpickle_sender, (self.context.context_id, self.dst_handle)

    def close(self):
        """Indicate this channel is closed to the remote side."""
        _vv and IOLOG.debug('%r.close()', self)
        self.context.send(Message.dead(handle=self.dst_handle))

    def send(self, data):
        """Send `data` to the remote."""
        _vv and IOLOG.debug('%r.send(%r..)', self, repr(data)[:100])
        self.context.send(Message.pickled(data, handle=self.dst_handle))


def _unpickle_sender(router, context_id, dst_handle):
    if not (isinstance(router, Router) and
            isinstance(context_id, (int, long)) and context_id >= 0 and
            isinstance(dst_handle, (int, long)) and dst_handle > 0):
        raise TypeError('cannot unpickle Sender: bad input')
    return Sender(Context(router, context_id), dst_handle)


class Receiver(object):
    notify = None
    raise_channelerror = True

    def __init__(self, router, handle=None, persist=True,
                 respondent=None, policy=None):
        self.router = router
        self.handle = handle  # Avoid __repr__ crash in add_handler()
        self.handle = router.add_handler(
            fn=self._on_receive,
            handle=handle,
            policy=policy,
            persist=persist,
            respondent=respondent,
        )
        self._latch = Latch()

    def __repr__(self):
        return 'Receiver(%r, %r)' % (self.router, self.handle)

    def to_sender(self):
        context = Context(self.router, mitogen.context_id)
        return Sender(context, self.handle)

    def _on_receive(self, msg):
        """Callback from the Stream; appends data to the internal queue."""
        _vv and IOLOG.debug('%r._on_receive(%r)', self, msg)
        self._latch.put(msg)
        if self.notify:
            self.notify(self)

    def close(self):
        if self.handle:
            self.router.del_handler(self.handle)
            self.handle = None
        self._latch.put(Message.dead())

    def empty(self):
        return self._latch.empty()

    def get(self, timeout=None, block=True, throw_dead=True):
        _vv and IOLOG.debug('%r.get(timeout=%r, block=%r)', self, timeout, block)
        msg = self._latch.get(timeout=timeout, block=block)
        if msg.is_dead and throw_dead:
            if msg.src_id == mitogen.context_id:
                raise ChannelError(ChannelError.local_msg)
            else:
                raise ChannelError(ChannelError.remote_msg)
        return msg

    def __iter__(self):
        while True:
            try:
                msg = self.get()
                msg.unpickle()  # Cause .remote_msg to be thrown.
                yield msg
            except ChannelError:
                return


class Channel(Sender, Receiver):
    def __init__(self, router, context, dst_handle, handle=None):
        Sender.__init__(self, context, dst_handle)
        Receiver.__init__(self, router, handle)

    def __repr__(self):
        return 'Channel(%s, %s)' % (
            Sender.__repr__(self),
            Receiver.__repr__(self)
        )


class Importer(object):
    """
    Import protocol implementation that fetches modules from the parent
    process.

    :param context: Context to communicate via.
    """
    def __init__(self, router, context, core_src, whitelist=(), blacklist=()):
        self._context = context
        self._present = {'mitogen': [
            'compat',
            'debug',
            'docker',
            'fakessh',
            'fork',
            'jail',
            'lxc',
            'master',
            'parent',
            'service',
            'setns',
            'ssh',
            'su',
            'sudo',
            'utils',
        ]}
        self._lock = threading.Lock()
        self.whitelist = list(whitelist) or ['']
        self.blacklist = list(blacklist) + [
            # 2.x generates needless imports for 'builtins', while 3.x does the
            # same for '__builtin__'. The correct one is built-in, the other
            # always a negative round-trip.
            'builtins',
            '__builtin__',
            # org.python.core imported by copy, pickle, xml.sax; breaks Jython,
            # but very unlikely to trigger a bug report.
            'org',
        ]

        # Presence of an entry in this map indicates in-flight GET_MODULE.
        self._callbacks = {}
        self._cache = {}
        if core_src:
            self._cache['mitogen.core'] = (
                'mitogen.core',
                None,
                'mitogen/core.py',
                zlib.compress(core_src, 9),
                [],
            )
        self._install_handler(router)

    def _install_handler(self, router):
        router.add_handler(
            fn=self._on_load_module,
            handle=LOAD_MODULE,
            policy=has_parent_authority,
        )

    def __repr__(self):
        return 'Importer()'

    def builtin_find_module(self, fullname):
        # imp.find_module() will always succeed for __main__, because it is a
        # built-in module. That means it exists on a special linked list deep
        # within the bowels of the interpreter. We must special case it.
        if fullname == '__main__':
            raise ImportError()

        parent, _, modname = fullname.rpartition('.')
        if parent:
            path = sys.modules[parent].__path__
        else:
            path = None

        fp, pathname, description = imp.find_module(modname, path)
        if fp:
            fp.close()

    def find_module(self, fullname, path=None):
        if hasattr(_tls, 'running'):
            return None

        _tls.running = True
        fullname = fullname.rstrip('.')
        try:
            pkgname, dot, _ = fullname.rpartition('.')
            _v and LOG.debug('%r.find_module(%r)', self, fullname)
            suffix = fullname[len(pkgname+dot):]
            if suffix not in self._present.get(pkgname, (suffix,)):
                _v and LOG.debug('%r: master doesn\'t know %r', self, fullname)
                return None

            pkg = sys.modules.get(pkgname)
            if pkg and getattr(pkg, '__loader__', None) is not self:
                _v and LOG.debug('%r: %r is submodule of a package we did not load',
                          self, fullname)
                return None

            # #114: explicitly whitelisted prefixes override any
            # system-installed package.
            if self.whitelist != ['']:
                if any(fullname.startswith(s) for s in self.whitelist):
                    return self

            try:
                self.builtin_find_module(fullname)
                _v and LOG.debug('%r: %r is available locally', self, fullname)
            except ImportError:
                _v and LOG.debug('find_module(%r) returning self', fullname)
                return self
        finally:
            del _tls.running

    def _refuse_imports(self, fullname):
        if is_blacklisted_import(self, fullname):
            raise ImportError('Refused: ' + fullname)

        f = sys._getframe(2)
        requestee = f.f_globals['__name__']

        if fullname == '__main__' and requestee == 'pkg_resources':
            # Anything that imports pkg_resources will eventually cause
            # pkg_resources to try and scan __main__ for its __requires__
            # attribute (pkg_resources/__init__.py::_build_master()). This
            # breaks any app that is not expecting its __main__ to suddenly be
            # sucked over a network and injected into a remote process, like
            # py.test.
            raise ImportError('Refused')

        if fullname == 'pbr':
            # It claims to use pkg_resources to read version information, which
            # would result in PEP-302 being used, but it actually does direct
            # filesystem access. So instead smodge the environment to override
            # any version that was defined. This will probably break something
            # later.
            os.environ['PBR_VERSION'] = '0.0.0'

    def _on_load_module(self, msg):
        if msg.is_dead:
            return

        tup = msg.unpickle()
        fullname = tup[0]
        _v and LOG.debug('Importer._on_load_module(%r)', fullname)

        self._lock.acquire()
        try:
            self._cache[fullname] = tup
            callbacks = self._callbacks.pop(fullname, [])
        finally:
            self._lock.release()

        for callback in callbacks:
            callback()

    def _request_module(self, fullname, callback):
        self._lock.acquire()
        try:
            present = fullname in self._cache
            if not present:
                funcs = self._callbacks.get(fullname)
                if funcs is not None:
                    _v and LOG.debug('_request_module(%r): in flight', fullname)
                    funcs.append(callback)
                else:
                    _v and LOG.debug('_request_module(%r): new request', fullname)
                    self._callbacks[fullname] = [callback]
                    self._context.send(Message(data=fullname, handle=GET_MODULE))
        finally:
            self._lock.release()

        if present:
            callback()

    def load_module(self, fullname):
        _v and LOG.debug('Importer.load_module(%r)', fullname)
        self._refuse_imports(fullname)

        event = threading.Event()
        self._request_module(fullname, event.set)
        event.wait()

        ret = self._cache[fullname]
        if ret[2] is None:
            raise ImportError('Master does not have %r' % (fullname,))

        pkg_present = ret[1]
        mod = sys.modules.setdefault(fullname, imp.new_module(fullname))
        mod.__file__ = self.get_filename(fullname)
        mod.__loader__ = self
        if pkg_present is not None:  # it's a package.
            mod.__path__ = []
            mod.__package__ = fullname
            self._present[fullname] = pkg_present
        else:
            mod.__package__ = fullname.rpartition('.')[0] or None

        # TODO: monster hack: work around modules now being imported as their
        # actual name, so when Ansible "apt.py" tries to "import apt", it gets
        # itself. Instead force absolute imports during compilation.
        flags = 0
        if fullname.startswith('ansible'):
            flags = 0x4000
        source = self.get_source(fullname)
        code = compile(source, mod.__file__, 'exec', flags, True)
        if PY3:
            exec(code, vars(mod))
        else:
            exec('exec code in vars(mod)')
        return mod

    def get_filename(self, fullname):
        if fullname in self._cache:
            return 'master:' + self._cache[fullname][2]

    def get_source(self, fullname):
        if fullname in self._cache:
            return zlib.decompress(self._cache[fullname][3])


class LogHandler(logging.Handler):
    def __init__(self, context):
        logging.Handler.__init__(self)
        self.context = context
        self.local = threading.local()

    def emit(self, rec):
        if rec.name == 'mitogen.io' or \
           getattr(self.local, 'in_emit', False):
            return

        self.local.in_emit = True
        try:
            msg = self.format(rec)
            encoded = '%s\x00%s\x00%s' % (rec.name, rec.levelno, msg)
            if isinstance(encoded, unicode):
                # Logging package emits both :(
                encoded = encoded.encode('utf-8')
            self.context.send(Message(data=encoded, handle=FORWARD_LOG))
        finally:
            self.local.in_emit = False


class Side(object):
    _fork_refs = weakref.WeakValueDictionary()

    def __init__(self, stream, fd, cloexec=True, keep_alive=True):
        self.stream = stream
        self.fd = fd
        self.closed = False
        self.keep_alive = keep_alive
        self._fork_refs[id(self)] = self
        if cloexec:
            set_cloexec(fd)
        set_nonblock(fd)

    def __repr__(self):
        return '<Side of %r fd %s>' % (self.stream, self.fd)

    @classmethod
    def _on_fork(cls):
        for side in list(cls._fork_refs.values()):
            side.close()

    def close(self):
        if not self.closed:
            _vv and IOLOG.debug('%r.close()', self)
            os.close(self.fd)
            self.closed = True

    def read(self, n=CHUNK_SIZE):
        s, disconnected = io_op(os.read, self.fd, n)
        if disconnected:
            return ''
        return s

    def write(self, s):
        if self.fd is None:
            return None

        written, disconnected = io_op(os.write, self.fd, s)
        if disconnected:
            return None
        return written


class BasicStream(object):
    receive_side = None
    transmit_side = None

    def on_disconnect(self, broker):
        LOG.debug('%r.on_disconnect()', self)
        if self.receive_side:
            broker.stop_receive(self)
            self.receive_side.close()
        if self.transmit_side:
            broker._stop_transmit(self)
            self.transmit_side.close()
        fire(self, 'disconnect')

    def on_shutdown(self, broker):
        _v and LOG.debug('%r.on_shutdown()', self)
        fire(self, 'shutdown')
        self.on_disconnect(broker)


class Stream(BasicStream):
    """
    :py:class:`BasicStream` subclass implementing mitogen's :ref:`stream
    protocol <stream-protocol>`.
    """
    #: If not ``None``, :py:class:`Router` stamps this into
    #: :py:attr:`Message.auth_id` of every message received on this stream.
    auth_id = None

    #: If not :data:`False`, indicates the stream has :attr:`auth_id` set and
    #: its value is the same as :data:`mitogen.context_id` or appears in
    #: :data:`mitogen.parent_ids`.
    is_privileged = False

    def __init__(self, router, remote_id, **kwargs):
        self._router = router
        self.remote_id = remote_id
        self.name = 'default'
        self.sent_modules = set()
        self.construct(**kwargs)
        self._input_buf = collections.deque()
        self._output_buf = collections.deque()
        self._input_buf_len = 0
        self._output_buf_len = 0

    def construct(self):
        pass

    def on_receive(self, broker):
        """Handle the next complete message on the stream. Raise
        :py:class:`StreamError` on failure."""
        _vv and IOLOG.debug('%r.on_receive()', self)

        buf = self.receive_side.read()
        if not buf:
            return self.on_disconnect(broker)

        if self._input_buf and self._input_buf_len < 128:
            self._input_buf[0] += buf
        else:
            self._input_buf.append(buf)

        self._input_buf_len += len(buf)
        while self._receive_one(broker):
            pass

    HEADER_FMT = '>LLLLLL'
    HEADER_LEN = struct.calcsize(HEADER_FMT)

    def _receive_one(self, broker):
        if self._input_buf_len < self.HEADER_LEN:
            return False

        msg = Message()
        msg.router = self._router
        (msg.dst_id, msg.src_id, msg.auth_id,
         msg.handle, msg.reply_to, msg_len) = struct.unpack(
            self.HEADER_FMT,
            self._input_buf[0][:self.HEADER_LEN],
        )

        if msg_len > self._router.max_message_size:
            LOG.error('Maximum message size exceeded (got %d, max %d)',
                      msg_len, self._router.max_message_size)
            self.on_disconnect(broker)
            return False

        total_len = msg_len + self.HEADER_LEN
        if self._input_buf_len < total_len:
            _vv and IOLOG.debug(
                '%r: Input too short (want %d, got %d)',
                self, msg_len, self._input_buf_len - self.HEADER_LEN
            )
            return False

        start = self.HEADER_LEN
        prev_start = start
        remain = total_len
        bits = []
        while remain:
            buf = self._input_buf.popleft()
            bit = buf[start:remain]
            bits.append(bit)
            remain -= len(bit) + start
            prev_start = start
            start = 0

        msg.data = ''.join(bits)
        self._input_buf.appendleft(buf[prev_start+len(bit):])
        self._input_buf_len -= total_len
        self._router._async_route(msg, self)
        return True

    def pending_bytes(self):
        return self._output_buf_len

    def on_transmit(self, broker):
        """Transmit buffered messages."""
        _vv and IOLOG.debug('%r.on_transmit()', self)

        if self._output_buf:
            buf = self._output_buf.popleft()
            written = self.transmit_side.write(buf)
            if not written:
                _v and LOG.debug('%r.on_transmit(): disconnection detected', self)
                self.on_disconnect(broker)
                return
            elif written != len(buf):
                self._output_buf.appendleft(buffer(buf, written))

            _vv and IOLOG.debug('%r.on_transmit() -> len %d', self, written)
            self._output_buf_len -= written

        if not self._output_buf:
            broker._stop_transmit(self)

    def _send(self, msg):
        _vv and IOLOG.debug('%r._send(%r)', self, msg)
        pkt = struct.pack(self.HEADER_FMT, msg.dst_id, msg.src_id,
                          msg.auth_id, msg.handle, msg.reply_to or 0,
                          len(msg.data)) + msg.data
        if not self._output_buf_len:
            self._router.broker._start_transmit(self)
        self._output_buf.append(pkt)
        self._output_buf_len += len(pkt)

    def send(self, msg):
        """Send `data` to `handle`, and tell the broker we have output. May
        be called from any thread."""
        self._router.broker.defer(self._send, msg)

    def on_shutdown(self, broker):
        """Override BasicStream behaviour of immediately disconnecting."""
        _v and LOG.debug('%r.on_shutdown(%r)', self, broker)

    def accept(self, rfd, wfd):
        # TODO: what is this os.dup for?
        self.receive_side = Side(self, os.dup(rfd))
        self.transmit_side = Side(self, os.dup(wfd))

    def __repr__(self):
        cls = type(self)
        return '%s.%s(%r)' % (cls.__module__, cls.__name__, self.name)


class Context(object):
    remote_name = None

    def __init__(self, router, context_id, name=None):
        self.router = router
        self.context_id = context_id
        self.name = name

    def __reduce__(self):
        return _unpickle_context, (self.context_id, self.name)

    def on_disconnect(self):
        _v and LOG.debug('%r.on_disconnect()', self)
        fire(self, 'disconnect')

    def send(self, msg):
        """send `obj` to `handle`, and tell the broker we have output. May
        be called from any thread."""
        msg.dst_id = self.context_id
        self.router.route(msg)

    def send_async(self, msg, persist=False):
        if self.router.broker._thread == threading.currentThread():  # TODO
            raise SystemError('Cannot making blocking call on broker thread')

        receiver = Receiver(self.router, persist=persist, respondent=self)
        msg.dst_id = self.context_id
        msg.reply_to = receiver.handle

        _v and LOG.debug('%r.send_async(%r)', self, msg)
        self.send(msg)
        return receiver

    def send_await(self, msg, deadline=None):
        """Send `msg` and wait for a response with an optional timeout."""
        receiver = self.send_async(msg)
        response = receiver.get(deadline)
        data = response.unpickle()
        _vv and IOLOG.debug('%r._send_await() -> %r', self, data)
        return data

    def __repr__(self):
        return 'Context(%s, %r)' % (self.context_id, self.name)


def _unpickle_context(router, context_id, name):
    if not (isinstance(router, Router) and
            isinstance(context_id, (int, long)) and context_id >= 0 and (
                (name is None) or
                (isinstance(name, basestring) and len(name) < 100))
            ):
        raise TypeError('cannot unpickle Context: bad input')
    return router.context_class(router, context_id, name)


class Poller(object):
    def __init__(self):
        self._rfds = {}
        self._wfds = {}

    _repr = 'Poller()'

    @property
    def readers(self):
        return list(self._rfds.items())

    @property
    def writers(self):
        return list(self._wfds.items())

    def __repr__(self):
        return self._repr

    def close(self):
        pass

    def start_receive(self, fd, data=None):
        self._rfds[fd] = data or fd

    def stop_receive(self, fd):
        self._rfds.pop(fd, None)

    def start_transmit(self, fd, data=None):
        self._wfds[fd] = data or fd

    def stop_transmit(self, fd):
        self._wfds.pop(fd, None)

    def poll(self, timeout=None):
        _vv and IOLOG.debug('%r.poll(%r)', self, timeout)
        IOLOG.debug('readers = %r', self._rfds)
        IOLOG.debug('writers = %r', self._wfds)
        (rfds, wfds, _), _ = io_op(select.select,
            self._rfds,
            self._wfds,
            (), timeout
        )

        for fd in rfds:
            _vv and IOLOG.debug('%r: POLLIN for %r', self, fd)
            yield self._rfds[fd]

        for fd in wfds:
            _vv and IOLOG.debug('%r: POLLOUT for %r', self, fd)
            yield self._wfds[fd]


class Latch(object):
    poller_class = Poller
    closed = False
    _waking = 0
    _sockets = []
    _allsockets = []

    def __init__(self):
        self._lock = threading.Lock()
        self._queue = []
        self._sleeping = []

    @classmethod
    def _on_fork(cls):
        cls._sockets = []
        while cls._allsockets:
            cls._allsockets.pop().close()

    def close(self):
        self._lock.acquire()
        try:
            self.closed = True
            while self._waking < len(self._sleeping):
                self._wake(self._sleeping[self._waking])
                self._waking += 1
        finally:
            self._lock.release()

    def empty(self):
        return len(self._queue) == 0

    def _tls_init(self):
        # pop() must be atomic, which is true for GIL-equipped interpreters.
        try:
            return self._sockets.pop()
        except IndexError:
            rsock, wsock = socket.socketpair()
            set_cloexec(rsock.fileno())
            set_cloexec(wsock.fileno())
            self._allsockets.extend((rsock, wsock))
            return rsock, wsock

    def get(self, timeout=None, block=True):
        _vv and IOLOG.debug('%r.get(timeout=%r, block=%r)',
                            self, timeout, block)
        self._lock.acquire()
        try:
            if self.closed:
                raise LatchError()
            i = len(self._sleeping)
            if len(self._queue) > i:
                _vv and IOLOG.debug('%r.get() -> %r', self, self._queue[i])
                return self._queue.pop(i)
            if not block:
                raise TimeoutError()
            rsock, wsock = self._tls_init()
            self._sleeping.append(wsock)
        finally:
            self._lock.release()

        return self._get_sleep(timeout, block, rsock, wsock)

    def _get_sleep(self, timeout, block, rsock, wsock):
        _vv and IOLOG.debug('%r._get_sleep(timeout=%r, block=%r)',
                            self, timeout, block)
        e = None
        poller = self.poller_class()
        poller.start_receive(rsock.fileno())
        try:
            try:
                list(poller.poll(timeout))
            except Exception:
                e = sys.exc_info()[1]
        finally:
            poller.close()

        self._lock.acquire()
        try:
            i = self._sleeping.index(wsock)
            del self._sleeping[i]
            self._sockets.append((rsock, wsock))
            if i >= self._waking:
                raise e or TimeoutError()
            self._waking -= 1
            if rsock.recv(2) != '\x7f':
                raise LatchError('internal error: received >1 wakeups')
            if e:
                raise e
            if self.closed:
                raise LatchError()
            _vv and IOLOG.debug('%r.get() wake -> %r', self, self._queue[i])
            return self._queue.pop(i)
        finally:
            self._lock.release()

    def put(self, obj):
        _vv and IOLOG.debug('%r.put(%r)', self, obj)
        self._lock.acquire()
        try:
            if self.closed:
                raise LatchError()
            self._queue.append(obj)

            if self._waking < len(self._sleeping):
                sock = self._sleeping[self._waking]
                self._waking += 1
                _vv and IOLOG.debug('%r.put() -> waking wfd=%r',
                                    self, sock.fileno())
                self._wake(sock)
        finally:
            self._lock.release()

    def _wake(self, sock):
        try:
            os.write(sock.fileno(), '\x7f')
        except OSError:
            e = sys.exc_info()[1]
            if e[0] != errno.EBADF:
                raise

    def __repr__(self):
        return 'Latch(%#x, size=%d, t=%r)' % (
            id(self),
            len(self._queue),
            threading.currentThread().name,
        )


class Waker(BasicStream):
    """
    :py:class:`BasicStream` subclass implementing the `UNIX self-pipe trick`_.
    Used to wake the multiplexer when another thread needs to modify its state
    (via a cross-thread function call).

    .. _UNIX self-pipe trick: https://cr.yp.to/docs/selfpipe.html
    """
    broker_ident = None

    def __init__(self, broker):
        self._broker = broker
        self._lock = threading.Lock()
        self._deferred = []

        rfd, wfd = os.pipe()
        self.receive_side = Side(self, rfd)
        self.transmit_side = Side(self, wfd)

    def __repr__(self):
        return 'Waker(%r rfd=%r, wfd=%r)' % (
            self._broker,
            self.receive_side.fd,
            self.transmit_side.fd,
        )

    @property
    def keep_alive(self):
        """
        Prevent immediate Broker shutdown while deferred functions remain.
        """
        self._lock.acquire()
        try:
            return len(self._deferred)
        finally:
            self._lock.release()

    def on_receive(self, broker):
        """
        Drain the pipe and fire callbacks. Reading multiple bytes is safe since
        new bytes corresponding to future .defer() calls are written only after
        .defer() takes _lock: either a byte we read corresponds to something
        already on the queue by the time we take _lock, or a byte remains
        buffered, causing another wake up, because it was written after we
        released _lock.
        """
        _vv and IOLOG.debug('%r.on_receive()', self)
        self.receive_side.read(128)
        self._lock.acquire()
        try:
            deferred = self._deferred
            self._deferred = []
        finally:
            self._lock.release()

        for func, args, kwargs in deferred:
            try:
                func(*args, **kwargs)
            except Exception:
                LOG.exception('defer() crashed: %r(*%r, **%r)',
                              func, args, kwargs)
                self._broker.shutdown()

    def defer(self, func, *args, **kwargs):
        if threading.currentThread().ident == self.broker_ident:
            _vv and IOLOG.debug('%r.defer() [immediate]', self)
            return func(*args, **kwargs)

        _vv and IOLOG.debug('%r.defer() [fd=%r]', self, self.transmit_side.fd)
        self._lock.acquire()
        try:
            self._deferred.append((func, args, kwargs))
        finally:
            self._lock.release()

        # Wake the multiplexer by writing a byte. If the broker is in the midst
        # of tearing itself down, the waker fd may already have been closed, so
        # ignore EBADF here.
        try:
            self.transmit_side.write(b(' '))
        except OSError:
            e = sys.exc_info()[1]
            if e[0] != errno.EBADF:
                raise


class IoLogger(BasicStream):
    """
    :py:class:`BasicStream` subclass that sets up redirection of a standard
    UNIX file descriptor back into the Python :py:mod:`logging` package.
    """
    _buf = ''

    def __init__(self, broker, name, dest_fd):
        self._broker = broker
        self._name = name
        self._log = logging.getLogger(name)
        self._rsock, self._wsock = socket.socketpair()
        os.dup2(self._wsock.fileno(), dest_fd)
        set_cloexec(self._wsock.fileno())

        self.receive_side = Side(self, self._rsock.fileno())
        self.transmit_side = Side(self, dest_fd, cloexec=False)
        self._broker.start_receive(self)

    def __repr__(self):
        return '<IoLogger %s>' % (self._name,)

    def _log_lines(self):
        while self._buf.find('\n') != -1:
            line, _, self._buf = self._buf.partition('\n')
            self._log.info('%s', line.rstrip('\n'))

    def on_shutdown(self, broker):
        """Shut down the write end of the logging socket."""
        _v and LOG.debug('%r.on_shutdown()', self)
        self._wsock.shutdown(socket.SHUT_WR)
        self._wsock.close()
        self.transmit_side.close()

    def on_receive(self, broker):
        _vv and IOLOG.debug('%r.on_receive()', self)
        buf = self.receive_side.read()
        if not buf:
            return self.on_disconnect(broker)

        self._buf += buf
        self._log_lines()


class Router(object):
    context_class = Context
    max_message_size = 128 * 1048576
    unidirectional = False

    def __init__(self, broker):
        self.broker = broker
        listen(broker, 'exit', self._on_broker_exit)

        # Here seems as good a place as any.
        global _v, _vv
        _v = logging.getLogger().level <= logging.DEBUG
        _vv = IOLOG.level <= logging.DEBUG

        #: context ID -> Stream
        self._stream_by_id = {}
        #: List of contexts to notify of shutdown.
        self._context_by_id = {}
        self._last_handle = itertools.count(1000)
        #: handle -> (persistent?, func(msg))
        self._handle_map = {}

    def __repr__(self):
        return 'Router(%r)' % (self.broker,)

    def on_stream_disconnect(self, stream):
        for context in self._context_by_id.values():
            stream_ = self._stream_by_id.get(context.context_id)
            if stream_ is stream:
                del self._stream_by_id[context.context_id]
                context.on_disconnect()

    def _on_broker_exit(self):
        while self._handle_map:
            _, (_, func, _) = self._handle_map.popitem()
            func(Message.dead())

    def register(self, context, stream):
        _v and LOG.debug('register(%r, %r)', context, stream)
        self._stream_by_id[context.context_id] = stream
        self._context_by_id[context.context_id] = context
        self.broker.start_receive(stream)
        listen(stream, 'disconnect', lambda: self.on_stream_disconnect(stream))

    def stream_by_id(self, dst_id):
        return self._stream_by_id.get(dst_id,
            self._stream_by_id.get(mitogen.parent_id))

    def del_handler(self, handle):
        del self._handle_map[handle]

    def add_handler(self, fn, handle=None, persist=True,
                    policy=None, respondent=None):
        handle = handle or self._last_handle.next()
        _vv and IOLOG.debug('%r.add_handler(%r, %r, %r)', self, fn, handle, persist)

        if respondent:
            assert policy is None
            def policy(msg, _stream):
                return msg.is_dead or msg.src_id == respondent.context_id
            def on_disconnect():
                if handle in self._handle_map:
                    fn(Message.dead())
                    del self._handle_map[handle]
            listen(respondent, 'disconnect', on_disconnect)

        self._handle_map[handle] = persist, fn, policy
        return handle

    def on_shutdown(self, broker):
        """Called during :py:meth:`Broker.shutdown`, informs callbacks
        registered with :py:meth:`add_handle_cb` the connection is dead."""
        _v and LOG.debug('%r.on_shutdown(%r)', self, broker)
        fire(self, 'shutdown')
        for handle, (persist, fn) in self._handle_map.iteritems():
            _v and LOG.debug('%r.on_shutdown(): killing %r: %r', self, handle, fn)
            fn(Message.dead())

    refused_msg = 'Refused by policy.'

    def _invoke(self, msg, stream):
        #IOLOG.debug('%r._invoke(%r)', self, msg)
        try:
            persist, fn, policy = self._handle_map[msg.handle]
        except KeyError:
            LOG.error('%r: invalid handle: %r', self, msg)
            if msg.reply_to and not msg.is_dead:
                msg.reply(Message.dead())
            return

        if policy and not policy(msg, stream):
            LOG.error('%r: policy refused message: %r', self, msg)
            if msg.reply_to:
                self.route(Message.pickled(
                    CallError(self.refused_msg),
                    dst_id=msg.src_id,
                    handle=msg.reply_to
                ))
            return

        if not persist:
            del self._handle_map[msg.handle]

        try:
            fn(msg)
        except Exception:
            LOG.exception('%r._invoke(%r): %r crashed', self, msg, fn)

    def _async_route(self, msg, in_stream=None):
        _vv and IOLOG.debug('%r._async_route(%r, %r)', self, msg, in_stream)
        if len(msg.data) > self.max_message_size:
            LOG.error('message too large (max %d bytes): %r',
                      self.max_message_size, msg)
            return

        # Perform source verification.
        if in_stream:
            parent = self._stream_by_id.get(mitogen.parent_id)
            expect = self._stream_by_id.get(msg.auth_id, parent)
            if in_stream != expect:
                LOG.error('%r: bad auth_id: got %r via %r, not %r: %r',
                          self, msg.auth_id, in_stream, expect, msg)
                return

            if msg.src_id != msg.auth_id:
                expect = self._stream_by_id.get(msg.src_id, parent)
                if in_stream != expect:
                    LOG.error('%r: bad src_id: got %r via %r, not %r: %r',
                              self, msg.src_id, in_stream, expect, msg)
                    return

            if in_stream.auth_id is not None:
                msg.auth_id = in_stream.auth_id

        if msg.dst_id == mitogen.context_id:
            return self._invoke(msg, in_stream)

        out_stream = self._stream_by_id.get(msg.dst_id)
        if out_stream is None:
            out_stream = self._stream_by_id.get(mitogen.parent_id)

        dead = False
        if out_stream is None:
            LOG.error('%r: no route for %r, my ID is %r',
                      self, msg, mitogen.context_id)
            dead = True

        if in_stream and self.unidirectional and not dead and \
           not (in_stream.is_privileged or out_stream.is_privileged):
            LOG.error('routing mode prevents forward of %r from %r -> %r',
                      msg, in_stream, out_stream)
            dead = True

        if dead:
            if msg.reply_to and not msg.is_dead:
                msg.reply(Message.dead(), router=self)
            return

        out_stream._send(msg)

    def route(self, msg):
        self.broker.defer(self._async_route, msg)


class Broker(object):
    poller_class = Poller
    _waker = None
    _thread = None
    shutdown_timeout = 3.0

    def __init__(self, poller_class=None):
        self._alive = True
        self._waker = Waker(self)
        self.defer = self._waker.defer
        self.poller = self.poller_class()
        self.poller.start_receive(
            self._waker.receive_side.fd,
            (self._waker.receive_side, self._waker.on_receive)
        )
        self._thread = threading.Thread(
            target=_profile_hook,
            args=('broker', self._broker_main),
            name='mitogen-broker'
        )
        self._thread.start()
        self._waker.broker_ident = self._thread.ident

    def start_receive(self, stream):
        _vv and IOLOG.debug('%r.start_receive(%r)', self, stream)
        side = stream.receive_side
        assert side and side.fd is not None
        self.defer(self.poller.start_receive,
                   side.fd, (side, stream.on_receive))

    def stop_receive(self, stream):
        _vv and IOLOG.debug('%r.stop_receive(%r)', self, stream)
        self.defer(self.poller.stop_receive, stream.receive_side.fd)

    def _start_transmit(self, stream):
        _vv and IOLOG.debug('%r._start_transmit(%r)', self, stream)
        side = stream.transmit_side
        assert side and side.fd is not None
        self.poller.start_transmit(side.fd, (side, stream.on_transmit))

    def _stop_transmit(self, stream):
        _vv and IOLOG.debug('%r._stop_transmit(%r)', self, stream)
        self.poller.stop_transmit(stream.transmit_side.fd)

    def keep_alive(self):
        it = (side.keep_alive for (_, (side, _)) in self.poller.readers)
        return sum(it, 0)

    def _call(self, stream, func):
        try:
            func(self)
        except Exception:
            LOG.exception('%r crashed', stream)
            stream.on_disconnect(self)

    def _loop_once(self, timeout=None):
        _vv and IOLOG.debug('%r._loop_once(%r)', self, timeout)
        for (side, func) in self.poller.poll(timeout):
            self._call(side.stream, func)

    def _broker_main(self):
        try:
            while self._alive:
                self._loop_once()

            fire(self, 'shutdown')
            for _, (side, _) in self.poller.readers + self.poller.writers:
                self._call(side.stream, side.stream.on_shutdown)

            deadline = time.time() + self.shutdown_timeout
            while self.keep_alive() and time.time() < deadline:
                self._loop_once(max(0, deadline - time.time()))

            if self.keep_alive():
                LOG.error('%r: some streams did not close gracefully. '
                          'The most likely cause for this is one or '
                          'more child processes still connected to '
                          'our stdout/stderr pipes.', self)

            for _, (side, _) in self.poller.readers + self.poller.writers:
                LOG.error('_broker_main() force disconnecting %r', side)
                side.stream.on_disconnect(self)
        except Exception:
            LOG.exception('_broker_main() crashed')

        fire(self, 'exit')

    def shutdown(self):
        _v and LOG.debug('%r.shutdown()', self)
        def _shutdown():
            self._alive = False
        self.defer(_shutdown)

    def join(self):
        self._thread.join()

    def __repr__(self):
        return 'Broker(%#x)' % (id(self),)


class ExternalContext(object):
    detached = False

    def _on_broker_shutdown(self):
        self.channel.close()

    def _on_broker_exit(self):
        if not self.profiling:
            os.kill(os.getpid(), signal.SIGTERM)

    def _on_shutdown_msg(self, msg):
        _v and LOG.debug('_on_shutdown_msg(%r)', msg)
        if not msg.is_dead:
            self.broker.shutdown()

    def _on_parent_disconnect(self):
        if self.detached:
            mitogen.parent_ids = []
            mitogen.parent_id = None
            LOG.info('Detachment complete')
        else:
            _v and LOG.debug('%r: parent stream is gone, dying.', self)
            self.broker.shutdown()

    def _sync(self, func):
        latch = Latch()
        self.broker.defer(lambda: latch.put(func()))
        return latch.get()

    def detach(self):
        self.detached = True
        stream = self.router.stream_by_id(mitogen.parent_id)
        if stream:  # not double-detach()'d
            os.setsid()
            self.parent.send_await(Message(handle=DETACHING))
            LOG.info('Detaching from %r; parent is %s', stream, self.parent)
            for x in range(20):
                pending = self._sync(lambda: stream.pending_bytes())
                if not pending:
                    break
                time.sleep(0.05)
            if pending:
                LOG.error('Stream had %d bytes after 2000ms', pending)
            self.broker.defer(stream.on_disconnect, self.broker)

    def _setup_master(self, max_message_size, profiling, unidirectional,
                      parent_id, context_id, in_fd, out_fd):
        Router.max_message_size = max_message_size
        self.profiling = profiling
        if profiling:
            enable_profiling()
        self.broker = Broker()
        self.router = Router(self.broker)
        self.router.undirectional = unidirectional
        self.router.add_handler(
            fn=self._on_shutdown_msg,
            handle=SHUTDOWN,
            policy=has_parent_authority,
        )
        self.master = Context(self.router, 0, 'master')
        if parent_id == 0:
            self.parent = self.master
        else:
            self.parent = Context(self.router, parent_id, 'parent')

        self.channel = Receiver(router=self.router,
                                handle=CALL_FUNCTION,
                                policy=has_parent_authority)
        self.stream = Stream(self.router, parent_id)
        self.stream.name = 'parent'
        self.stream.accept(in_fd, out_fd)
        self.stream.receive_side.keep_alive = False

        listen(self.stream, 'disconnect', self._on_parent_disconnect)
        listen(self.broker, 'shutdown', self._on_broker_shutdown)
        listen(self.broker, 'exit', self._on_broker_exit)

        os.close(in_fd)

    def _reap_first_stage(self):
        try:
            os.wait()  # Reap first stage.
        except OSError:
            pass  # No first stage exists (e.g. fakessh)

    def _setup_logging(self, debug, log_level):
        root = logging.getLogger()
        root.setLevel(log_level)
        root.handlers = [LogHandler(self.master)]
        if debug:
            enable_debug_logging()

    def _setup_importer(self, importer, core_src_fd, whitelist, blacklist):
        if importer:
            importer._install_handler(self.router)
            importer._context = self.parent
        else:
            if core_src_fd:
                fp = os.fdopen(101, 'r', 1)
                try:
                    core_size = int(fp.readline())
                    core_src = fp.read(core_size)
                    # Strip "ExternalContext.main()" call from last line.
                    core_src = '\n'.join(core_src.splitlines()[:-1])
                finally:
                    fp.close()
            else:
                core_src = None

            importer = Importer(self.router, self.parent,
                                core_src, whitelist, blacklist)

        self.importer = importer
        self.router.importer = importer
        sys.meta_path.append(self.importer)

    def _setup_package(self):
        global mitogen
        mitogen = imp.new_module('mitogen')
        mitogen.__package__ = 'mitogen'
        mitogen.__path__ = []
        mitogen.__loader__ = self.importer
        mitogen.main = lambda *args, **kwargs: (lambda func: None)
        mitogen.core = sys.modules['__main__']
        mitogen.core.__file__ = 'x/mitogen/core.py'  # For inspect.getsource()
        mitogen.core.__loader__ = self.importer
        sys.modules['mitogen'] = mitogen
        sys.modules['mitogen.core'] = mitogen.core
        del sys.modules['__main__']

    def _setup_globals(self, version, context_id, parent_ids):
        mitogen.__version__ = version
        mitogen.is_master = False
        mitogen.context_id = context_id
        mitogen.parent_ids = parent_ids
        mitogen.parent_id = parent_ids[0]

    def _setup_stdio(self):
        # We must open this prior to closing stdout, otherwise it will recycle
        # a standard handle, the dup2() will not error, and on closing it, we
        # lose a standrd handle, causing later code to again recycle a standard
        # handle.
        fp = open('/dev/null')

        # When sys.stdout was opened by the runtime, overwriting it will not
        # cause close to be called. However when forking from a child that
        # previously used fdopen, overwriting it /will/ cause close to be
        # called. So we must explicitly close it before IoLogger overwrites the
        # file descriptor, otherwise the assignment below will cause stdout to
        # be closed.
        sys.stdout.close()
        sys.stdout = None

        try:
            os.dup2(fp.fileno(), 0)
            os.dup2(fp.fileno(), 1)
            os.dup2(fp.fileno(), 2)
        finally:
            fp.close()

        self.stdout_log = IoLogger(self.broker, 'stdout', 1)
        self.stderr_log = IoLogger(self.broker, 'stderr', 2)
        # Reopen with line buffering.
        sys.stdout = os.fdopen(1, 'w', 1)

    def _dispatch_one(self, msg):
        data = msg.unpickle(throw=False)
        _v and LOG.debug('_dispatch_calls(%r)', data)

        modname, klass, func, args, kwargs = data
        obj = __import__(modname, {}, {}, [''])
        if klass:
            obj = getattr(obj, klass)
        fn = getattr(obj, func)
        if getattr(fn, 'mitogen_takes_econtext', None):
            kwargs.setdefault('econtext', self)
        if getattr(fn, 'mitogen_takes_router', None):
            kwargs.setdefault('router', self.router)
        return fn(*args, **kwargs)

    def _dispatch_calls(self):
        for msg in self.channel:
            try:
                msg.reply(self._dispatch_one(msg))
            except Exception:
                e = sys.exc_info()[1]
                _v and LOG.debug('_dispatch_calls: %s', e)
                msg.reply(CallError(e))
        self.dispatch_stopped = True

    def main(self, parent_ids, context_id, debug, profiling, log_level,
             unidirectional, max_message_size, version, in_fd=100, out_fd=1,
             core_src_fd=101, setup_stdio=True, setup_package=True,
             importer=None, whitelist=(), blacklist=()):
        self._setup_master(max_message_size, profiling, unidirectional,
                           parent_ids[0], context_id, in_fd, out_fd)
        try:
            try:
                self._setup_logging(debug, log_level)
                self._setup_importer(importer, core_src_fd, whitelist, blacklist)
                self._reap_first_stage()
                if setup_package:
                    self._setup_package()
                self._setup_globals(version, context_id, parent_ids)
                if setup_stdio:
                    self._setup_stdio()

                self.router.register(self.parent, self.stream)

                sys.executable = os.environ.pop('ARGV0', sys.executable)
                _v and LOG.debug('Connected to %s; my ID is %r, PID is %r',
                                 self.parent, context_id, os.getpid())
                _v and LOG.debug('Recovered sys.executable: %r', sys.executable)

                _profile_hook('main', self._dispatch_calls)
                _v and LOG.debug('ExternalContext.main() normal exit')
            except KeyboardInterrupt:
                LOG.debug('KeyboardInterrupt received, exiting gracefully.')
            except BaseException:
                LOG.exception('ExternalContext.main() crashed')
                raise
        finally:
            self.broker.shutdown()
            self.broker.join()
