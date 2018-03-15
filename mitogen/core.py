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

import Queue
import cPickle
import cStringIO
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
import zlib

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
ALLOCATE_ID = 104
SHUTDOWN = 105
LOAD_MODULE = 106

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


class CallError(Error):
    def __init__(self, e):
        s = '%s.%s: %s' % (type(e).__module__, type(e).__name__, e)
        tb = sys.exc_info()[2]
        if tb:
            s += '\n'
            s += ''.join(traceback.format_tb(tb))
        Error.__init__(self, s)

    def __reduce__(self):
        return (_unpickle_call_error, (self[0],))


def _unpickle_call_error(s):
    assert type(s) is str and len(s) < 10000
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


class Dead(object):
    def __hash__(self):
        return hash(Dead)

    def __eq__(self, other):
        return type(other) is Dead

    def __ne__(self, other):
        return type(other) is not Dead

    def __reduce__(self):
        return (_unpickle_dead, ())

    def __repr__(self):
        return '<Dead>'


def _unpickle_dead():
    return _DEAD


_DEAD = Dead()


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


def restart(func, *args):
    while True:
        try:
            return func(*args)
        except (select.error, OSError), e:
            if e[0] != errno.EINTR:
                raise


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
    fcntl.fcntl(fd, fcntl.F_SETFD, flags | fcntl.FD_CLOEXEC)


def set_nonblock(fd):
    flags = fcntl.fcntl(fd, fcntl.F_GETFL)
    fcntl.fcntl(fd, fcntl.F_SETFL, flags | os.O_NONBLOCK)


def set_block(fd):
    flags = fcntl.fcntl(fd, fcntl.F_GETFL)
    fcntl.fcntl(fd, fcntl.F_SETFL, flags & ~os.O_NONBLOCK)


def io_op(func, *args):
    try:
        return func(*args), False
    except OSError, e:
        _vv and IOLOG.debug('io_op(%r) -> OSError: %s', func, e)
        if e.errno not in (errno.EIO, errno.ECONNRESET, errno.EPIPE):
            raise
        return None, True


def enable_debug_logging():
    root = logging.getLogger()
    root.setLevel(logging.DEBUG)
    IOLOG.setLevel(logging.DEBUG)
    fp = open('/tmp/mitogen.%s.log' % (os.getpid(),), 'w', 1)
    fp.write('Parent PID: %s\n' % (os.getppid(),))
    fp.write('Created by:\n\n%s\n\n' % (''.join(traceback.format_stack()),))
    set_cloexec(fp.fileno())
    handler = logging.StreamHandler(fp)
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

    router = None
    receiver = None

    def __init__(self, **kwargs):
        self.src_id = mitogen.context_id
        self.auth_id = mitogen.context_id
        vars(self).update(kwargs)

    def _unpickle_context(self, context_id, name):
        return _unpickle_context(self.router, context_id, name)

    def _find_global(self, module, func):
        """Return the class implementing `module_name.class_name` or raise
        `StreamError` if the module is not whitelisted."""
        if module == __name__:
            if func == '_unpickle_call_error':
                return _unpickle_call_error
            elif func == '_unpickle_dead':
                return _unpickle_dead
            elif func == '_unpickle_context':
                return self._unpickle_context

        raise StreamError('cannot unpickle %r/%r', module, func)

    @classmethod
    def pickled(cls, obj, **kwargs):
        self = cls(**kwargs)
        try:
            self.data = cPickle.dumps(obj, protocol=2)
        except cPickle.PicklingError, e:
            self.data = cPickle.dumps(CallError(e), protocol=2)
        return self

    def reply(self, obj, **kwargs):
        kwargs.setdefault('handle', self.reply_to)
        self.router.route(
            self.pickled(obj, dst_id=self.src_id, **kwargs)
        )

    def unpickle(self, throw=True, throw_dead=True):
        """Deserialize `data` into an object."""
        _vv and IOLOG.debug('%r.unpickle()', self)
        fp = cStringIO.StringIO(self.data)
        unpickler = cPickle.Unpickler(fp)
        unpickler.find_global = self._find_global

        try:
            # Must occur off the broker thread.
            obj = unpickler.load()
        except (TypeError, ValueError), ex:
            raise StreamError('invalid message: %s', ex)

        if throw:
            if obj == _DEAD and throw_dead:
                raise ChannelError(ChannelError.remote_msg)
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

    def close(self):
        """Indicate this channel is closed to the remote side."""
        _vv and IOLOG.debug('%r.close()', self)
        self.context.send(
            Message.pickled(
                _DEAD,
                handle=self.dst_handle
            )
        )

    def put(self, data):
        """Send `data` to the remote."""
        _vv and IOLOG.debug('%r.put(%r..)', self, data[:100])
        self.context.send(
            Message.pickled(
                data,
                handle=self.dst_handle
            )
        )


class Receiver(object):
    notify = None
    raise_channelerror = True

    def __init__(self, router, handle=None, persist=True, respondent=None):
        self.router = router
        self.handle = handle  # Avoid __repr__ crash in add_handler()
        self.handle = router.add_handler(self._on_receive, handle,
                                         persist, respondent)
        self._latch = Latch()

    def __repr__(self):
        return 'Receiver(%r, %r)' % (self.router, self.handle)

    def _on_receive(self, msg):
        """Callback from the Stream; appends data to the internal queue."""
        _vv and IOLOG.debug('%r._on_receive(%r)', self, msg)
        self._latch.put(msg)
        if self.notify:
            self.notify(self)

    def close(self):
        self._latch.put(_DEAD)

    def empty(self):
        return self._latch.empty()

    def get(self, timeout=None, block=True):
        _vv and IOLOG.debug('%r.get(timeout=%r, block=%r)', self, timeout, block)
        msg = self._latch.get(timeout=timeout, block=block)
        #IOLOG.debug('%r.get() got %r', self, msg)

        if msg == _DEAD:
            raise ChannelError(ChannelError.local_msg)
        return msg

    def __iter__(self):
        while True:
            try:
                yield self.get()
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
            'compat.pkgutil',
            'fakessh',
            'master',
            'parent',
            'ssh',
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
        ]

        # Presence of an entry in this map indicates in-flight GET_MODULE.
        self._callbacks = {}
        router.add_handler(self._on_load_module, LOAD_MODULE)
        self._cache = {}
        if core_src:
            self._cache['mitogen.core'] = (
                'mitogen.core',
                None,
                'mitogen/core.py',
                zlib.compress(core_src, 9),
                [],
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
        if msg == _DEAD:
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
        exec code in vars(mod)
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
    def __init__(self, stream, fd, keep_alive=True):
        self.stream = stream
        self.fd = fd
        self.keep_alive = keep_alive
        set_nonblock(fd)

    def __repr__(self):
        return '<Side of %r fd %s>' % (self.stream, self.fd)

    def fileno(self):
        if self.fd is None:
            raise StreamError('%r.fileno() called but no FD set', self)
        return self.fd

    def close(self):
        if self.fd is not None:
            _vv and IOLOG.debug('%r.close()', self)
            os.close(self.fd)
            self.fd = None

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
        broker.stop_receive(self)
        broker.stop_transmit(self)
        if self.receive_side:
            self.receive_side.close()
        if self.transmit_side:
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

    def __init__(self, router, remote_id, **kwargs):
        self._router = router
        self.remote_id = remote_id
        self.name = 'default'
        self.sent_modules = set()
        self.construct(**kwargs)
        self._input_buf = collections.deque()
        self._input_buf_len = 0
        self._output_buf = collections.deque()

    def construct(self):
        pass

    def on_receive(self, broker):
        """Handle the next complete message on the stream. Raise
        :py:class:`StreamError` on failure."""
        _vv and IOLOG.debug('%r.on_receive()', self)

        buf = self.receive_side.read()
        if buf:
            if self._input_buf and self._input_buf_len < 128:
                self._input_buf[0] += buf
            else:
                self._input_buf.append(buf)
            self._input_buf_len += len(buf)
            while self._receive_one(broker):
                pass
        else:
            return self.on_disconnect(broker)

    HEADER_FMT = '>hhhLLL'
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

        if (self._input_buf_len - self.HEADER_LEN) < msg_len:
            _vv and IOLOG.debug(
                '%r: Input too short (want %d, got %d)',
                self, msg_len, self._input_buf_len - self.HEADER_LEN
            )
            return False

        start = self.HEADER_LEN
        prev_start = start
        remain = msg_len + start
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
        self._input_buf_len -= self.HEADER_LEN + msg_len
        self._router._async_route(msg, self)
        return True

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
                self._output_buf.appendleft(buf[written:])

            _vv and IOLOG.debug('%r.on_transmit() -> len %d', self, written)

        if not self._output_buf:
            broker.stop_transmit(self)

    def _send(self, msg):
        _vv and IOLOG.debug('%r._send(%r)', self, msg)
        pkt = struct.pack('>hhhLLL', msg.dst_id, msg.src_id, msg.auth_id,
                          msg.handle, msg.reply_to or 0, len(msg.data)
        ) + msg.data
        self._output_buf.append(pkt)
        self._router.broker.start_transmit(self)

    def send(self, msg):
        """Send `data` to `handle`, and tell the broker we have output. May
        be called from any thread."""
        self._router.broker.defer(self._send, msg)

    def on_disconnect(self, broker):
        super(Stream, self).on_disconnect(broker)
        self._router.on_disconnect(self, broker)

    def on_shutdown(self, broker):
        """Override BasicStream behaviour of immediately disconnecting."""
        _v and LOG.debug('%r.on_shutdown(%r)', self, broker)

    def accept(self, rfd, wfd):
        # TODO: what is this os.dup for?
        self.receive_side = Side(self, os.dup(rfd))
        self.transmit_side = Side(self, os.dup(wfd))
        set_cloexec(self.receive_side.fd)
        set_cloexec(self.transmit_side.fd)

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

    def on_disconnect(self, broker):
        _v and LOG.debug('Parent stream is gone, dying.')
        fire(self, 'disconnect')
        broker.shutdown()

    def on_shutdown(self, broker):
        pass

    def send(self, msg):
        """send `obj` to `handle`, and tell the broker we have output. May
        be called from any thread."""
        msg.dst_id = self.context_id
        self.router.route(msg)

    def send_async(self, msg, persist=False):
        if self.router.broker._thread == threading.currentThread():  # TODO
            raise SystemError('Cannot making blocking call on broker thread')

        receiver = Receiver(self.router, persist=persist, respondent=self)
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
    assert isinstance(router, Router)
    assert isinstance(context_id, (int, long)) and context_id > 0
    assert isinstance(name, basestring) and len(name) < 100
    return router.context_class(router, context_id, name)


class Latch(object):
    def __init__(self):
        self.lock = threading.Lock()
        self.queue = []
        self.wake_socks = []

    def _tls_init(self):
        if not hasattr(_tls, 'rsock'):
            _tls.rsock, _tls.wsock = socket.socketpair()
            set_cloexec(_tls.rsock.fileno())
            set_cloexec(_tls.wsock.fileno())

    def empty(self):
        return len(self.queue) == 0

    def get(self, timeout=None, block=True):
        self.lock.acquire()
        try:
            if self.queue:
                return self.queue.pop(0)
            if not block:
                raise TimeoutError()
            self._tls_init()
            self.wake_socks.append(_tls.wsock)
        finally:
            self.lock.release()

        rfds, _, _ = restart(select.select, [_tls.rsock], [], [], timeout)
        assert len(rfds) or timeout is not None

        self.lock.acquire()
        try:
            if _tls.wsock in self.wake_socks:
                # Nothing woke us, remove stale entry.
                self.wake_socks.remove(_tls.wsock)
                raise TimeoutError()

            assert _tls.rsock in rfds
            _tls.rsock.recv(1)
            return self.queue.pop(0)
        finally:
            self.lock.release()

    def put(self, obj):
        _vv and IOLOG.debug('%r.put(%r)', self, obj)
        self.lock.acquire()
        try:
            self.queue.append(obj)
            woken = len(self.wake_socks) > 0
            if woken:
                self._wake(self.wake_socks.pop(0))
        finally:
            self.lock.release()
        _v and LOG.debug('put() done. woken? %s', woken)

    def _wake(self, sock):
        try:
            os.write(sock.fileno(), '\x00')
        except OSError, e:
            if e[0] != errno.EBADF:
                raise


class Waker(BasicStream):
    """
    :py:class:`BasicStream` subclass implementing the
    `UNIX self-pipe trick`_. Used internally to wake the IO multiplexer when
    some of its state has been changed by another thread.

    .. _UNIX self-pipe trick: https://cr.yp.to/docs/selfpipe.html
    """
    def __init__(self, broker):
        self._broker = broker
        rfd, wfd = os.pipe()
        set_cloexec(rfd)
        set_cloexec(wfd)
        self.receive_side = Side(self, rfd)
        self.transmit_side = Side(self, wfd)

    def __repr__(self):
        return 'Waker(%r)' % (self._broker,)

    def on_receive(self, broker):
        """
        Read a byte from the self-pipe.
        """
        self.receive_side.read(256)

    def wake(self):
        """
        Write a byte to the self-pipe, causing the IO multiplexer to wake up.
        Nothing is written if the current thread is the IO multiplexer thread.
        """
        _vv and IOLOG.debug('%r.wake() [fd=%r]', self, self.transmit_side.fd)
        if threading.currentThread() != self._broker._thread:
            try:
                self.transmit_side.write(' ')
            except OSError, e:
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
        set_cloexec(self._rsock.fileno())
        set_cloexec(self._wsock.fileno())

        self.receive_side = Side(self, self._rsock.fileno())
        self.transmit_side = Side(self, dest_fd)
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
        buf = os.read(self.receive_side.fd, CHUNK_SIZE)
        if not buf:
            return self.on_disconnect(broker)

        self._buf += buf
        self._log_lines()


class Router(object):
    context_class = Context

    def __init__(self, broker):
        self.broker = broker
        listen(broker, 'shutdown', self.on_broker_shutdown)

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
        self._handle_map = {
            ADD_ROUTE: (True, self._on_add_route)
        }

    def __repr__(self):
        return 'Router(%r)' % (self.broker,)

    def stream_by_id(self, dst_id):
        return self._stream_by_id.get(dst_id,
            self._stream_by_id.get(mitogen.parent_id))

    def on_disconnect(self, stream, broker):
        """Invoked by Stream.on_disconnect()."""
        for context in self._context_by_id.itervalues():
            stream_ = self._stream_by_id.get(context.context_id)
            if stream_ is stream:
                del self._stream_by_id[context.context_id]
                context.on_disconnect(broker)

    def on_broker_shutdown(self):
        for context in self._context_by_id.itervalues():
            context.on_shutdown(self.broker)

        for _, func in self._handle_map.itervalues():
            func(_DEAD)

    def add_route(self, target_id, via_id):
        _v and LOG.debug('%r.add_route(%r, %r)', self, target_id, via_id)
        try:
            self._stream_by_id[target_id] = self._stream_by_id[via_id]
        except KeyError:
            LOG.error('%r: cant add route to %r via %r: no such stream',
                      self, target_id, via_id)

    def _on_add_route(self, msg):
        if msg != _DEAD:
            target_id, via_id = map(int, msg.data.split('\x00'))
            self.add_route(target_id, via_id)

    def register(self, context, stream):
        _v and LOG.debug('register(%r, %r)', context, stream)
        self._stream_by_id[context.context_id] = stream
        self._context_by_id[context.context_id] = context
        self.broker.start_receive(stream)

    def add_handler(self, fn, handle=None, persist=True, respondent=None):
        handle = handle or self._last_handle.next()
        _vv and IOLOG.debug('%r.add_handler(%r, %r, %r)', self, fn, handle, persist)
        self._handle_map[handle] = persist, fn

        if respondent:
            def on_disconnect():
                if handle in self._handle_map:
                    fn(_DEAD)
                    del self._handle_map[handle]
            listen(respondent, 'disconnect', on_disconnect)

        return handle

    def on_shutdown(self, broker):
        """Called during :py:meth:`Broker.shutdown`, informs callbacks
        registered with :py:meth:`add_handle_cb` the connection is dead."""
        _v and LOG.debug('%r.on_shutdown(%r)', self, broker)
        fire(self, 'shutdown')
        for handle, (persist, fn) in self._handle_map.iteritems():
            _v and LOG.debug('%r.on_shutdown(): killing %r: %r', self, handle, fn)
            fn(_DEAD)

    def _invoke(self, msg):
        #IOLOG.debug('%r._invoke(%r)', self, msg)
        try:
            persist, fn = self._handle_map[msg.handle]
        except KeyError:
            LOG.error('%r: invalid handle: %r', self, msg)
            return

        if not persist:
            del self._handle_map[msg.handle]

        try:
            fn(msg)
        except Exception:
            LOG.exception('%r._invoke(%r): %r crashed', self, msg, fn)

    def _async_route(self, msg, stream=None):
        _vv and IOLOG.debug('%r._async_route(%r, %r)', self, msg, stream)
        # Perform source verification.
        if stream is not None:
            expected_stream = self._stream_by_id.get(msg.auth_id,
                self._stream_by_id.get(mitogen.parent_id))
            if stream != expected_stream:
                LOG.error('%r: bad source: got auth ID %r from %r, should be from %r',
                          self, msg, stream, expected_stream)
            if stream.auth_id is not None:
                msg.auth_id = stream.auth_id

        if msg.dst_id == mitogen.context_id:
            return self._invoke(msg)

        stream = self._stream_by_id.get(msg.dst_id)
        if stream is None:
            stream = self._stream_by_id.get(mitogen.parent_id)

        if stream is None:
            LOG.error('%r: no route for %r, my ID is %r',
                      self, msg, mitogen.context_id)
            return

        stream.send(msg)

    def route(self, msg):
        self.broker.defer(self._async_route, msg)


class Broker(object):
    _waker = None
    _thread = None
    shutdown_timeout = 3.0

    def __init__(self):
        self._alive = True
        self._queue = Queue.Queue()
        self._readers = []
        self._writers = []
        self._waker = Waker(self)
        self.start_receive(self._waker)
        self._thread = threading.Thread(
            target=_profile_hook,
            args=('broker', self._broker_main),
            name='mitogen-broker'
        )
        self._thread.start()

    def defer(self, func, *args, **kwargs):
        if threading.currentThread() == self._thread:
            func(*args, **kwargs)
        else:
            self._queue.put((func, args, kwargs))
            self._waker.wake()

    def _list_discard(self, lst, value):
        try:
            lst.remove(value)
        except ValueError:
            pass

    def _list_add(self, lst, value):
        if value not in lst:
            lst.append(value)

    def start_receive(self, stream):
        _vv and IOLOG.debug('%r.start_receive(%r)', self, stream)
        assert stream.receive_side and stream.receive_side.fd is not None
        self.defer(self._list_add, self._readers, stream.receive_side)

    def stop_receive(self, stream):
        IOLOG.debug('%r.stop_receive(%r)', self, stream)
        self.defer(self._list_discard, self._readers, stream.receive_side)

    def start_transmit(self, stream):
        IOLOG.debug('%r.start_transmit(%r)', self, stream)
        assert stream.transmit_side and stream.transmit_side.fd is not None
        self.defer(self._list_add, self._writers, stream.transmit_side)

    def stop_transmit(self, stream):
        IOLOG.debug('%r.stop_transmit(%r)', self, stream)
        self.defer(self._list_discard, self._writers, stream.transmit_side)

    def _call(self, stream, func):
        try:
            func(self)
        except Exception:
            LOG.exception('%r crashed', stream)
            stream.on_disconnect(self)

    def _run_defer(self):
        while not self._queue.empty():
            func, args, kwargs = self._queue.get()
            try:
                func(*args, **kwargs)
            except Exception:
                LOG.exception('defer() crashed: %r(*%r, **%r)',
                              func, args, kwargs)
                self.shutdown()

    def _loop_once(self, timeout=None):
        _vv and IOLOG.debug('%r._loop_once(%r)', self, timeout)
        self._run_defer()

        #IOLOG.debug('readers = %r', self._readers)
        #IOLOG.debug('writers = %r', self._writers)
        rsides, wsides, _ = restart(select.select,
            self._readers,
            self._writers,
            (), timeout
        )

        for side in rsides:
            _vv and IOLOG.debug('%r: POLLIN for %r', self, side)
            self._call(side.stream, side.stream.on_receive)

        for side in wsides:
            _vv and IOLOG.debug('%r: POLLOUT for %r', self, side)
            self._call(side.stream, side.stream.on_transmit)

    def keep_alive(self):
        return (sum((side.keep_alive for side in self._readers), 0) +
                (not self._queue.empty()))

    def _broker_main(self):
        try:
            while self._alive:
                self._loop_once()

            self._run_defer()
            fire(self, 'shutdown')

            for side in set(self._readers).union(self._writers):
                self._call(side.stream, side.stream.on_shutdown)

            deadline = time.time() + self.shutdown_timeout
            while self.keep_alive() and time.time() < deadline:
                self._loop_once(max(0, deadline - time.time()))

            if self.keep_alive():
                LOG.error('%r: some streams did not close gracefully. '
                          'The most likely cause for this is one or '
                          'more child processes still connected to '
                          'our stdout/stderr pipes.', self)

            for side in set(self._readers).union(self._writers):
                LOG.error('_broker_main() force disconnecting %r', side)
                side.stream.on_disconnect(self)
        except Exception:
            LOG.exception('_broker_main() crashed')

        fire(self, 'exit')

    def shutdown(self):
        _v and LOG.debug('%r.shutdown()', self)
        self._alive = False
        self._waker.wake()

    def join(self):
        self._thread.join()

    def __repr__(self):
        return 'Broker()'


class ExternalContext(object):
    def _on_broker_shutdown(self):
        self.channel.close()

    def _on_broker_exit(self):
        if not self.profiling:
            os.kill(os.getpid(), signal.SIGTERM)

    def _on_shutdown_msg(self, msg):
        _v and LOG.debug('_on_shutdown_msg(%r)', msg)
        if msg != _DEAD and msg.src_id != mitogen.parent_id:
            LOG.warning('Ignoring SHUTDOWN from non-parent: %r', msg)
            return
        self.broker.shutdown()

    def _setup_master(self, profiling, parent_id, context_id, in_fd, out_fd):
        self.profiling = profiling
        if profiling:
            enable_profiling()
        self.broker = Broker()
        self.router = Router(self.broker)
        self.router.add_handler(self._on_shutdown_msg, SHUTDOWN)
        self.master = Context(self.router, 0, 'master')
        if parent_id == 0:
            self.parent = self.master
        else:
            self.parent = Context(self.router, parent_id, 'parent')

        self.channel = Receiver(self.router, CALL_FUNCTION)
        self.stream = Stream(self.router, parent_id)
        self.stream.name = 'parent'
        self.stream.accept(in_fd, out_fd)
        self.stream.receive_side.keep_alive = False

        listen(self.broker, 'shutdown', self._on_broker_shutdown)
        listen(self.broker, 'exit', self._on_broker_exit)

        os.close(in_fd)
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

    def _setup_importer(self, core_src_fd, whitelist, blacklist):
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

        self.importer = Importer(self.router, self.parent, core_src,
                                 whitelist, blacklist)
        self.router.importer = self.importer
        sys.meta_path.append(self.importer)

    def _setup_package(self, context_id, parent_ids):
        global mitogen
        mitogen = imp.new_module('mitogen')
        mitogen.__package__ = 'mitogen'
        mitogen.__path__ = []
        mitogen.__loader__ = self.importer
        mitogen.is_master = False
        mitogen.context_id = context_id
        mitogen.parent_ids = parent_ids
        mitogen.parent_id = parent_ids[0]
        mitogen.main = lambda *args, **kwargs: (lambda func: None)
        mitogen.core = sys.modules['__main__']
        mitogen.core.__file__ = 'x/mitogen/core.py'  # For inspect.getsource()
        mitogen.core.__loader__ = self.importer
        sys.modules['mitogen'] = mitogen
        sys.modules['mitogen.core'] = mitogen.core
        del sys.modules['__main__']

    def _setup_stdio(self):
        self.stdout_log = IoLogger(self.broker, 'stdout', 1)
        self.stderr_log = IoLogger(self.broker, 'stderr', 2)
        # Reopen with line buffering.
        sys.stdout = os.fdopen(1, 'w', 1)

        fp = open('/dev/null')
        try:
            os.dup2(fp.fileno(), 0)
        finally:
            fp.close()

    def _dispatch_one(self, msg):
        data = msg.unpickle(throw=False)
        _v and LOG.debug('_dispatch_calls(%r)', data)
        if msg.auth_id not in mitogen.parent_ids:
            LOG.warning('CALL_FUNCTION from non-parent %r', msg.auth_id)

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
            except Exception, e:
                _v and LOG.debug('_dispatch_calls: %s', e)
                msg.reply(CallError(e))
        self.dispatch_stopped = True

    def main(self, parent_ids, context_id, debug, profiling, log_level,
             in_fd=100, out_fd=1, core_src_fd=101, setup_stdio=True,
             whitelist=(), blacklist=()):
        self._setup_master(profiling, parent_ids[0], context_id, in_fd, out_fd)
        try:
            try:
                self._setup_logging(debug, log_level)
                self._setup_importer(core_src_fd, whitelist, blacklist)
                self._setup_package(context_id, parent_ids)
                if setup_stdio:
                    self._setup_stdio()

                self.router.register(self.parent, self.stream)

                sys.executable = os.environ.pop('ARGV0', sys.executable)
                _v and LOG.debug('Connected to %s; my ID is %r, PID is %r',
                                 self.parent, context_id, os.getpid())
                _v and LOG.debug('Recovered sys.executable: %r', sys.executable)

                _profile_hook('main', self._dispatch_calls)
                _v and LOG.debug('ExternalContext.main() normal exit')
            except BaseException:
                LOG.exception('ExternalContext.main() crashed')
                raise
        finally:
            self.broker.shutdown()
            self.broker.join()
