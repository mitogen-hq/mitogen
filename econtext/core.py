"""
This module implements most package functionality, but remains separate from
non-essential code in order to reduce its size, since it is also serves as the
bootstrap implementation sent to every new slave context.
"""

import Queue
import cPickle
import cStringIO
import errno
import fcntl
import hmac
import imp
import itertools
import logging
import os
import random
import select
import sha
import socket
import struct
import sys
import threading
import time
import traceback
import zlib


LOG = logging.getLogger('econtext')
IOLOG = logging.getLogger('econtext.io')
IOLOG.setLevel(logging.INFO)

GET_MODULE = 100
CALL_FUNCTION = 101
FORWARD_LOG = 102
ADD_ROUTE = 103

CHUNK_SIZE = 16384


if __name__ == 'econtext.core':
    # When loaded using import mechanism, ExternalContext.main() will not have
    # a chance to set the synthetic econtext global, so just import it here.
    import econtext
else:
    # When loaded as __main__, ensure classes and functions gain a __module__
    # attribute consistent with the host process, so that pickling succeeds.
    __name__ = 'econtext.core'


class Error(Exception):
    """Base for all exceptions raised by this module."""
    def __init__(self, fmt, *args):
        Exception.__init__(self, fmt % args)


class CallError(Error):
    """Raised when :py:meth:`Context.call() <econtext.master.Context.call>`
    fails. A copy of the traceback from the external context is appended to the
    exception message.
    """
    def __init__(self, e):
        name = '%s.%s' % (type(e).__module__, type(e).__name__)
        tb = sys.exc_info()[2]
        if tb:
            stack = ''.join(traceback.format_tb(tb))
        else:
            stack = ''
        Error.__init__(self, 'call failed: %s: %s\n%s', name, e, stack)


class ChannelError(Error):
    """Raised when a channel dies or has been closed."""


class StreamError(Error):
    """Raised when a stream cannot be established."""


class TimeoutError(StreamError):
    """Raised when a timeout occurs on a stream."""


class Dead(object):
    def __eq__(self, other):
        return type(other) is Dead

    def __repr__(self):
        return '<Dead>'


#: Sentinel value used to represent :py:class:`Channel` disconnection.
_DEAD = Dead()


def set_cloexec(fd):
    flags = fcntl.fcntl(fd, fcntl.F_GETFD)
    fcntl.fcntl(fd, fcntl.F_SETFD, flags | fcntl.FD_CLOEXEC)


def io_op(func, *args):
    """
    When connected over a TTY (i.e. sudo), disconnection of the remote end is
    signalled by EIO, rather than an empty read like sockets or pipes. Ideally
    this will be replaced later by a 'goodbye' message to avoid reading from a
    disconnected endpoint, allowing for more robust error reporting.

    When connected over a socket (e.g. econtext.master.create_child()),
    ECONNRESET may be triggered by any read or write.
    """
    try:
        return func(*args), False
    except OSError, e:
        IOLOG.debug('io_op(%r) -> OSError: %s', func, e)
        if e.errno not in (errno.EIO, errno.ECONNRESET):
            raise
        return None, True


def enable_debug_logging():
    root = logging.getLogger()
    root.setLevel(logging.DEBUG)
    IOLOG.setLevel(logging.DEBUG)
    fp = open('/tmp/econtext.%s.log' % (os.getpid(),), 'w', 1)
    set_cloexec(fp.fileno())
    handler = logging.StreamHandler(fp)
    handler.formatter = logging.Formatter(
        '%(asctime)s %(levelname).1s %(name)s: %(message)s',
        '%H:%M:%S'
    )
    root.handlers.insert(0, handler)


class Message(object):
    dst_id = None
    src_id = None
    handle = None
    reply_to = None
    data = None

    def __init__(self, **kwargs):
        self.src_id = econtext.context_id
        vars(self).update(kwargs)

    _find_global = None

    @classmethod
    def pickled(cls, obj, **kwargs):
        self = cls(**kwargs)
        try:
            self.data = cPickle.dumps(obj, protocol=2)
        except cPickle.PicklingError, e:
            self.data = cPickle.dumps(CallError(str(e)), protocol=2)
        return self

    def unpickle(self):
        """Deserialize `data` into an object."""
        IOLOG.debug('%r.unpickle()', self)
        fp = cStringIO.StringIO(self.data)
        unpickler = cPickle.Unpickler(fp)
        if self._find_global:
            unpickler.find_global = self._find_global
        try:
            return unpickler.load()
        except (TypeError, ValueError), ex:
            raise StreamError('invalid message: %s', ex)

    def __repr__(self):
        return 'Message(%r, %r, %r, %r, %r..)' % (
            self.dst_id, self.src_id, self.handle, self.reply_to,
            (self.data or '')[:50]
        )


class Channel(object):
    def __init__(self, context, handle=None):
        self._context = context
        self._queue = Queue.Queue()
        self.handle = handle  # Avoid __repr__ crash in add_handler()
        self.handle = context.add_handler(self._receive, handle)

    def _receive(self, msg):
        """Callback from the Stream; appends data to the internal queue."""
        IOLOG.debug('%r._receive(%r)', self, msg)
        self._queue.put(msg)

    def close(self):
        """Indicate this channel is closed to the remote side."""
        IOLOG.debug('%r.close()', self)
        self._context.send(self.handle, _DEAD)

    def put(self, data):
        """Send `data` to the remote."""
        IOLOG.debug('%r.send(%r)', self, data)
        self._context.send(self.handle, data)

    def get(self, timeout=None):
        """Receive an object, or ``None`` if `timeout` is reached."""
        IOLOG.debug('%r.on_receive(timeout=%r)', self, timeout)
        if timeout:
            timeout += time.time()

        msg = None
        while msg is None and (timeout is None or timeout < time.time()):
            try:
                msg = self._queue.get(True, 0.5)
            except Queue.Empty:
                continue

        if msg is None:
            return

        IOLOG.debug('%r.on_receive() got %r', self, msg)
        if msg == _DEAD:
            raise ChannelError('Channel closed by local end.')

        # Must occur off the broker thread.
        data = msg.unpickle()
        if data == _DEAD:
            raise ChannelError('Channel closed by remote end.')

        if isinstance(data, CallError):
            raise data

        return msg, data

    def __iter__(self):
        """Yield objects from this channel until it is closed."""
        while True:
            try:
                yield self.get()
            except ChannelError:
                return

    def __repr__(self):
        return 'Channel(%r, %r)' % (self._context, self.handle)


class Importer(object):
    """
    Import protocol implementation that fetches modules from the parent
    process.

    :param context: Context to communicate via.
    """
    def __init__(self, context, core_src):
        self._context = context
        self._present = {'econtext': [
            'econtext.ansible',
            'econtext.compat',
            'econtext.compat.pkgutil',
            'econtext.master',
            'econtext.ssh',
            'econtext.sudo',
            'econtext.utils',
        ]}
        self.tls = threading.local()
        self._cache = {}
        if core_src:
            self._cache['econtext.core'] = (
                None,
                'econtext/core.py',
                zlib.compress(core_src),
            )

    def __repr__(self):
        return 'Importer()'

    def find_module(self, fullname, path=None):
        if hasattr(self.tls, 'running'):
            return None

        self.tls.running = True
        fullname = fullname.rstrip('.')
        try:
            pkgname, _, _ = fullname.rpartition('.')
            LOG.debug('%r.find_module(%r)', self, fullname)
            if fullname not in self._present.get(pkgname, (fullname,)):
                LOG.debug('%r: master doesn\'t know %r', self, fullname)
                return None

            pkg = sys.modules.get(pkgname)
            if pkg and getattr(pkg, '__loader__', None) is not self:
                LOG.debug('%r: %r is submodule of a package we did not load',
                          self, fullname)
                return None

            try:
                __import__(fullname, {}, {}, [''])
                LOG.debug('%r: %r is available locally', self, fullname)
            except ImportError:
                LOG.debug('find_module(%r) returning self', fullname)
                return self
        finally:
            del self.tls.running

    def load_module(self, fullname):
        LOG.debug('Importer.load_module(%r)', fullname)
        try:
            ret = self._cache[fullname]
        except KeyError:
            self._cache[fullname] = ret = (
                self._context.send_await(
                    Message(data=fullname, handle=GET_MODULE)
                ).unpickle()
            )

        if ret is None:
            raise ImportError('Master does not have %r' % (fullname,))

        pkg_present = ret[0]
        mod = sys.modules.setdefault(fullname, imp.new_module(fullname))
        mod.__file__ = self.get_filename(fullname)
        mod.__loader__ = self
        if pkg_present is not None:  # it's a package.
            mod.__path__ = []
            mod.__package__ = fullname
            self._present[fullname] = pkg_present
        else:
            mod.__package__ = fullname.rpartition('.')[0] or None
        code = compile(self.get_source(fullname), mod.__file__, 'exec')
        exec code in vars(mod)
        return mod

    def get_filename(self, fullname):
        if fullname in self._cache:
            return 'master:' + self._cache[fullname][1]

    def get_source(self, fullname):
        if fullname in self._cache:
            return zlib.decompress(self._cache[fullname][2])


class LogHandler(logging.Handler):
    def __init__(self, context):
        logging.Handler.__init__(self)
        self.context = context
        self.local = threading.local()

    def emit(self, rec):
        if rec.name == 'econtext.io' or \
           getattr(self.local, 'in_emit', False):
            return

        self.local.in_emit = True
        try:
            msg = self.format(rec)
            encoded = '%s\x00%s\x00%s' % (rec.name, rec.levelno, msg)
            self.context.send(Message(data=encoded, handle=FORWARD_LOG))
        finally:
            self.local.in_emit = False


class Side(object):
    """
    Represent a single side of a :py:class:`BasicStream`. This exists to allow
    streams implemented using unidirectional (e.g. UNIX pipe) and bidirectional
    (e.g. UNIX socket) file descriptors to operate identically.
    """
    def __init__(self, stream, fd, keep_alive=True):
        #: The :py:class:`Stream` for which this is a read or write side.
        self.stream = stream
        #: Integer file descriptor to perform IO on.
        self.fd = fd
        #: If ``True``, causes presence of this side in :py:class:`Broker`'s
        #: active reader set to defer shutdown until the side is disconnected.
        self.keep_alive = keep_alive

    def __repr__(self):
        return '<Side of %r fd %s>' % (self.stream, self.fd)

    def fileno(self):
        """Return :py:attr:`fd` if it is not ``None``, otherwise raise
        ``StreamError``. This method is implemented so that :py:class:`Side`
        can be used directly by :py:func:`select.select`."""
        if self.fd is None:
            raise StreamError('%r.fileno() called but no FD set', self)
        return self.fd

    def close(self):
        """Call :py:func:`os.close` on :py:attr:`fd` if it is not ``None``,
        then set it to ``None``."""
        if self.fd is not None:
            IOLOG.debug('%r.close()', self)
            os.close(self.fd)
            self.fd = None

    def read(self, n=CHUNK_SIZE):
        s, disconnected = io_op(os.read, self.fd, n)
        if disconnected:
            return ''
        return s

    def write(self, s):
        written, disconnected = io_op(os.write, self.fd, s[:CHUNK_SIZE])
        if disconnected:
            return None
        return written


class BasicStream(object):
    """

    .. method:: on_disconnect (broker)

        Called by :py:class:`Broker` to force disconnect the stream. The base
        implementation simply closes :py:attr:`receive_side` and
        :py:attr:`transmit_side` and unregisters the stream from the broker.

    .. method:: on_receive (broker)

        Called by :py:class:`Broker` when the stream's :py:attr:`receive_side` has
        been marked readable using :py:meth:`Broker.start_receive` and the
        broker has detected the associated file descriptor is ready for
        reading.

        Subclasses must implement this method if
        :py:meth:`Broker.start_receive` is ever called on them, and the method
        must call :py:meth:`on_disconect` if reading produces an empty string.

    .. method:: on_transmit (broker)

        Called by :py:class:`Broker` when the stream's :py:attr:`transmit_side`
        has been marked writeable using :py:meth:`Broker.start_transmit` and
        the broker has detected the associated file descriptor is ready for
        writing.

        Subclasses must implement this method if
        :py:meth:`Broker.start_transmit` is ever called on them.

    .. method:: on_shutdown (broker)

        Called by :py:meth:`Broker.shutdown` to allow the stream time to
        gracefully shutdown. The base implementation simply called
        :py:meth:`on_disconnect`.

    """
    #: A :py:class:`Side` representing the stream's receive file descriptor.
    receive_side = None

    #: A :py:class:`Side` representing the stream's transmit file descriptor.
    transmit_side = None

    def on_disconnect(self, broker):
        LOG.debug('%r.on_disconnect()', self)
        broker.stop_receive(self)
        broker.stop_transmit(self)
        self.receive_side.close()
        self.transmit_side.close()

    def on_shutdown(self, broker):
        LOG.debug('%r.on_shutdown()', self)
        self.on_disconnect(broker)


class Stream(BasicStream):
    """
    :py:class:`BasicStream` subclass implementing econtext's :ref:`stream
    protocol <stream-protocol>`.
    """
    _input_buf = ''
    _output_buf = ''
    message_class = Message

    def __init__(self, router, remote_id, key, **kwargs):
        self._router = router
        self.remote_id = remote_id
        self.key = key
        self._rhmac = hmac.new(key, digestmod=sha)
        self._whmac = self._rhmac.copy()
        self.name = 'default'
        self.construct(**kwargs)

    def construct(self):
        pass

    def on_receive(self, broker):
        """Handle the next complete message on the stream. Raise
        :py:class:`StreamError` on failure."""
        IOLOG.debug('%r.on_receive()', self)

        buf = self.receive_side.read()
        if buf is None:
            buf = ''

        self._input_buf += buf
        while self._receive_one(broker):
            pass

        if not buf:
            return self.on_disconnect(broker)

    HEADER_FMT = '>20shhLLL'
    HEADER_LEN = struct.calcsize(HEADER_FMT)
    MAC_LEN = sha.digest_size

    def _receive_one(self, broker):
        if len(self._input_buf) < self.HEADER_LEN:
            return False

        msg = Message()
        (msg_mac, msg.dst_id, msg.src_id,
         msg.handle, msg.reply_to, msg_len) = struct.unpack(
            self.HEADER_FMT,
            self._input_buf[:self.HEADER_LEN]
        )

        if (len(self._input_buf) - self.HEADER_LEN) < msg_len:
            IOLOG.debug('%r: Input too short (want %d, got %d)',
                        self, msg_len, len(self._input_buf) - self.HEADER_LEN)
            return False

        self._rhmac.update(self._input_buf[
            self.MAC_LEN : (msg_len + self.HEADER_LEN)
        ])
        expected_mac = self._rhmac.digest()
        if msg_mac != expected_mac:
            raise StreamError('bad MAC: %r != got %r; %r',
                              msg_mac.encode('hex'),
                              expected_mac.encode('hex'),
                              self._input_buf[24:msg_len+24])

        msg.data = self._input_buf[self.HEADER_LEN:self.HEADER_LEN+msg_len]
        self._input_buf = self._input_buf[self.HEADER_LEN+msg_len:]
        self._router.route(msg)
        return True

    def on_transmit(self, broker):
        """Transmit buffered messages."""
        IOLOG.debug('%r.on_transmit()', self)
        written = self.transmit_side.write(self._output_buf)
        if written is None:
            LOG.debug('%r.on_transmit(): disconnection detected', self)
            self.on_disconnect()
            return

        IOLOG.debug('%r.on_transmit() -> len %d', self, written)
        self._output_buf = self._output_buf[written:]
        if not self._output_buf:
            broker.stop_transmit(self)

    def send(self, msg):
        """Send `data` to `handle`, and tell the broker we have output. May
        be called from any thread."""
        IOLOG.debug('%r._send(%r)', self, msg)
        pkt = struct.pack('>hhLLL', msg.dst_id, msg.src_id,
                          msg.handle, msg.reply_to or 0, len(msg.data)
        ) + msg.data
        self._whmac.update(pkt)
        self._output_buf += self._whmac.digest() + pkt
        self._router.broker.start_transmit(self)

    def on_disconnect(self, broker):
        super(Stream, self).on_disconnect(broker)
        self._router.on_disconnect(self, broker)

    def on_shutdown(self, broker):
        """Override BasicStream behaviour of immediately disconnecting."""
        LOG.debug('%r.on_shutdown(%r)', self, broker)

    def accept(self, rfd, wfd):
        self.receive_side = Side(self, os.dup(rfd))
        self.transmit_side = Side(self, os.dup(wfd))
        set_cloexec(self.receive_side.fd)
        set_cloexec(self.transmit_side.fd)

    def __repr__(self):
        cls = type(self)
        return '%s.%s(%r)' % (cls.__module__, cls.__name__, self.name)


class Context(object):
    """
    Represent a remote context regardless of connection method.
    """
    remote_name = None

    def __init__(self, router, context_id, name=None, key=None):
        self.router = router
        self.context_id = context_id
        self.name = name
        self.key = key or ('%016x' % random.getrandbits(128))
        #: handle -> (persistent?, func(msg))
        self._handle_map = {}
        self._last_handle = itertools.count(1000)

    def add_handler(self, fn, handle=None, persist=True):
        """Invoke `fn(msg)` for each Message sent to `handle` from this
        context. Unregister after one invocation if `persist` is ``False``. If
        `handle` is ``None``, a new handle is allocated and returned."""
        handle = handle or self._last_handle.next()
        IOLOG.debug('%r.add_handler(%r, %r, %r)', self, fn, handle, persist)
        self._handle_map[handle] = persist, fn
        return handle

    def on_shutdown(self, broker):
        """Called during :py:meth:`Broker.shutdown`, informs callbacks
        registered with :py:meth:`add_handle_cb` the connection is dead."""
        LOG.debug('%r.on_shutdown(%r)', self, broker)
        for handle, (persist, fn) in self._handle_map.iteritems():
            LOG.debug('%r.on_shutdown(): killing %r: %r', self, handle, fn)
            fn(_DEAD)

    def on_disconnect(self, broker):
        LOG.debug('Parent stream is gone, dying.')
        broker.shutdown()

    def send(self, msg):
        """send `obj` to `handle`, and tell the broker we have output. May
        be called from any thread."""
        msg.dst_id = self.context_id
        if msg.src_id is None:
            msg.src_id = econtext.context_id
        self.router.route(msg)

    def send_await(self, msg, deadline=None):
        """Send `msg` and wait for a response with an optional timeout."""
        if self.router.broker._thread == threading.currentThread():  # TODO
            raise SystemError('Cannot making blocking call on broker thread')

        queue = Queue.Queue()
        msg.reply_to = self.add_handler(queue.put, persist=False)
        LOG.debug('%r.send_await(%r)', self, msg)

        self.send(msg)
        try:
            msg = queue.get(True, deadline)
        except Queue.Empty:
            # self.broker.on_thread(self.stream.on_disconnect, self.broker)
            raise TimeoutError('deadline exceeded.')

        if msg == _DEAD:
            raise StreamError('lost connection during call.')

        IOLOG.debug('%r._send_await() -> %r', self, msg)
        return msg

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

    def __repr__(self):
        return 'Context(%s, %r)' % (self.context_id, self.name)


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
        broker.start_receive(self)

    def __repr__(self):
        return 'Waker(%r)' % (self._broker,)

    def wake(self):
        """
        Write a byte to the self-pipe, causing the IO multiplexer to wake up.
        Nothing is written if the current thread is the IO multiplexer thread.
        """
        if threading.currentThread() != self._broker._thread and \
           self.transmit_side.fd:
            os.write(self.transmit_side.fd, ' ')

    def on_receive(self, broker):
        """
        Read a byte from the self-pipe.
        """
        os.read(self.receive_side.fd, 256)


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
        LOG.debug('%r.on_shutdown()', self)
        self._wsock.shutdown(socket.SHUT_WR)
        self._wsock.close()
        self.transmit_side.close()

    def on_receive(self, broker):
        IOLOG.debug('%r.on_receive()', self)
        buf = os.read(self.receive_side.fd, CHUNK_SIZE)
        if not buf:
            return self.on_disconnect(broker)

        self._buf += buf
        self._log_lines()


class Router(object):
    """
    Route messages between parent and child contexts, and invoke handlers
    defined on our parent context. Router.route() straddles the Broker and user
    threads, it is save to call from anywhere.
    """
    parent_context = None

    def __init__(self, broker):
        self.broker = broker
        #: context ID -> Stream
        self._stream_by_id = {}
        #: List of contexts to notify of shutdown.
        self._context_by_id = {}

    def __repr__(self):
        return 'Router(%r)' % (self.broker,)

    def on_disconnect(self, stream, broker):
        """Invoked by Stream.on_disconnect()."""
        for context in self._context_by_id.itervalues():
            stream_ = self._stream_by_id.get(context.context_id)
            if stream_ is stream:
                del self._stream_by_id[context.context_id]
                context.on_disconnect(broker)

    def on_shutdown(self, broker):
        for context in self._context_by_id.itervalues():
            context.on_shutdown(broker)

    def add_route(self, target_id, via_id):
        LOG.debug('%r.add_route(%r, %r)', self, target_id, via_id)
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
        LOG.debug('register(%r, %r)', context, stream)
        self._stream_by_id[context.context_id] = stream
        self._context_by_id[context.context_id] = context
        self.broker.start_receive(stream)

    def _route(self, msg):
        IOLOG.debug('%r._route(%r)', self, msg)
        context = self._context_by_id.get(msg.src_id)
        if context and msg.dst_id == econtext.context_id:
            context._invoke(msg)
            return

        stream = self._stream_by_id.get(msg.dst_id)
        if stream is None:
            LOG.error('%r: no route for %r, my ID is %r',
                      self, msg, econtext.context_id)
            return

        stream.send(msg)

    def route(self, msg):
        self.broker.on_thread(self._route, msg)


class Broker(object):
    """
    Responsible for tracking contexts, their associated streams and I/O
    multiplexing.
    """
    _waker = None
    _thread = None

    #: Seconds grace to allow :py:class:`Streams <Stream>` to shutdown
    #: gracefully before force-disconnecting them during :py:meth:`shutdown`.
    shutdown_timeout = 3.0

    def __init__(self):
        self.on_shutdown = []
        self._alive = True
        self._queue = Queue.Queue()
        self._readers = set()
        self._writers = set()
        self._waker = Waker(self)
        self._thread = threading.Thread(target=self._broker_main,
                                        name='econtext-broker')
        self._thread.start()

    def on_thread(self, func, *args, **kwargs):
        if threading.currentThread() == self._thread:
            func(*args, **kwargs)
        else:
            self._queue.put((func, args, kwargs))
            if self._waker:
                self._waker.wake()

    def start_receive(self, stream):
        """Mark the :py:attr:`receive_side <Stream.receive_side>` on `stream` as
        ready for reading. May be called from any thread. When the associated
        file descriptor becomes ready for reading,
        :py:meth:`BasicStream.on_transmit` will be called."""
        IOLOG.debug('%r.start_receive(%r)', self, stream)
        self.on_thread(self._readers.add, stream.receive_side)

    def stop_receive(self, stream):
        IOLOG.debug('%r.stop_receive(%r)', self, stream)
        self.on_thread(self._readers.discard, stream.receive_side)

    def start_transmit(self, stream):
        IOLOG.debug('%r.start_transmit(%r)', self, stream)
        assert stream.transmit_side
        self.on_thread(self._writers.add, stream.transmit_side)

    def stop_transmit(self, stream):
        IOLOG.debug('%r.stop_transmit(%r)', self, stream)
        self.on_thread(self._writers.discard, stream.transmit_side)

    def _call(self, stream, func):
        try:
            func(self)
        except Exception:
            LOG.exception('%r crashed', stream)
            stream.on_disconnect(self)

    def _run_on_thread(self):
        while not self._queue.empty():
            func, args, kwargs = self._queue.get()
            try:
                func(*args, **kwargs)
            except Exception:
                LOG.exception('on_thread() crashed: %r(*%r, **%r)',
                              func, args, kwargs)
                self.shutdown()

    def _loop_once(self, timeout=None):
        IOLOG.debug('%r._loop_once(%r)', self, timeout)
        self._run_on_thread()

        #IOLOG.debug('readers = %r', self._readers)
        #IOLOG.debug('writers = %r', self._writers)
        rsides, wsides, _ = select.select(self._readers, self._writers,
                                          (), timeout)
        for side in rsides:
            IOLOG.debug('%r: POLLIN for %r', self, side.stream)
            self._call(side.stream, side.stream.on_receive)

        for side in wsides:
            IOLOG.debug('%r: POLLOUT for %r', self, side.stream)
            self._call(side.stream, side.stream.on_transmit)

    def keep_alive(self):
        """Return ``True`` if any reader's :py:attr:`Side.keep_alive`
        attribute is ``True``, or any :py:class:`Context` is still registered
        that is not the master. Used to delay shutdown while some important
        work is in progress (e.g. log draining)."""
        return sum(side.keep_alive for side in self._readers)

    def _broker_main(self):
        """Handle events until :py:meth:`shutdown`. On shutdown, invoke
        :py:meth:`Stream.on_shutdown` for every active stream, then allow up to
        :py:attr:`shutdown_timeout` seconds for the streams to unregister
        themselves before forcefully calling
        :py:meth:`Stream.on_disconnect`."""
        try:
            while self._alive:
                self._loop_once()

            for func in self.on_shutdown:
                func(self)

            for side in self._readers | self._writers:
                self._call(side.stream, side.stream.on_shutdown)

            deadline = time.time() + self.shutdown_timeout
            while self.keep_alive() and time.time() < deadline:
                self._loop_once(max(0, deadline - time.time()))

            if self.keep_alive():
                LOG.error('%r: some streams did not close gracefully. '
                          'The most likely cause for this is one or '
                          'more child processes still connected to '
                          'our stdout/stderr pipes.', self)

            for side in self._readers | self._writers:
                LOG.error('_broker_main() force disconnecting %r', side)
                side.stream.on_disconnect(self)
        except Exception:
            LOG.exception('_broker_main() crashed')

    def shutdown(self):
        """Request broker gracefully disconnect streams and stop."""
        LOG.debug('%r.shutdown()', self)
        self._alive = False
        self._waker.wake()

    def join(self):
        """Wait for the broker to stop, expected to be called after
        :py:meth:`shutdown`."""
        self._thread.join()

    def __repr__(self):
        return 'Broker()'


class ExternalContext(object):
    """
    External context implementation.

    .. attribute:: broker

        The :py:class:`econtext.core.Broker` instance.

    .. attribute:: context

            The :py:class:`econtext.core.Context` instance.

    .. attribute:: channel

            The :py:class:`econtext.core.Channel` over which
            :py:data:`CALL_FUNCTION` requests are received.

    .. attribute:: stdout_log

        The :py:class:`econtext.core.IoLogger` connected to ``stdout``.

    .. attribute:: importer

        The :py:class:`econtext.core.Importer` instance.

    .. attribute:: stdout_log

        The :py:class:`IoLogger` connected to ``stdout``.

    .. attribute:: stderr_log

        The :py:class:`IoLogger` connected to ``stderr``.
    """
    def _setup_master(self, parent_id, context_id, key, in_fd, out_fd):
        self.broker = Broker()
        self.router = Router(self.broker)
        self.broker.on_shutdown.append(self.router.on_shutdown)
        self.master = Context(self.router, 0, 'master')
        if parent_id == 0:
            self.parent = self.master
        else:
            self.parent = Context(self.router, parent_id, 'parent')

        self.channel = Channel(self.master, CALL_FUNCTION)
        self.stream = Stream(self.router, parent_id, key)
        self.stream.name = 'parent'
        self.stream.accept(in_fd, out_fd)
        self.stream.receive_side.keep_alive = False

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

    def _setup_importer(self, core_src_fd):
        if core_src_fd:
            with os.fdopen(101, 'r', 1) as fp:
                core_size = int(fp.readline())
                core_src = fp.read(core_size)
                # Strip "ExternalContext.main()" call from last line.
                core_src = '\n'.join(core_src.splitlines()[:-1])
                fp.close()
        else:
            core_src = None

        self.importer = Importer(self.parent, core_src)
        sys.meta_path.append(self.importer)

    def _setup_package(self, context_id):
        global econtext
        econtext = imp.new_module('econtext')
        econtext.__package__ = 'econtext'
        econtext.__path__ = []
        econtext.__loader__ = self.importer
        econtext.slave = True
        econtext.context_id = context_id
        econtext.core = sys.modules['__main__']
        econtext.core.__file__ = 'x/econtext/core.py'  # For inspect.getsource()
        econtext.core.__loader__ = self.importer
        sys.modules['econtext'] = econtext
        sys.modules['econtext.core'] = econtext.core
        del sys.modules['__main__']

    def _setup_stdio(self):
        self.stdout_log = IoLogger(self.broker, 'stdout', 1)
        self.stderr_log = IoLogger(self.broker, 'stderr', 2)
        # Reopen with line buffering.
        sys.stdout = os.fdopen(1, 'w', 1)

        fp = file('/dev/null')
        try:
            os.dup2(fp.fileno(), 0)
        finally:
            fp.close()

    def _dispatch_calls(self):
        for msg, data in self.channel:
            LOG.debug('_dispatch_calls(%r)', msg)
            with_context, modname, klass, func, args, kwargs = data
            if with_context:
                args = (self,) + args

            try:
                obj = __import__(modname, {}, {}, [''])
                if klass:
                    obj = getattr(obj, klass)
                fn = getattr(obj, func)
                ret = fn(*args, **kwargs)
                self.master.send(Message.pickled(ret, handle=msg.reply_to))
            except Exception, e:
                LOG.debug('_dispatch_calls: %s', e)
                e = CallError(str(e))
                self.master.send(Message.pickled(e, handle=msg.reply_to))

    def main(self, parent_id, context_id, key, debug, log_level,
             in_fd=100, out_fd=1, core_src_fd=101, setup_stdio=True):
        self._setup_master(parent_id, context_id, key, in_fd, out_fd)
        try:
            try:
                self._setup_logging(debug, log_level)
                self._setup_importer(core_src_fd)
                self._setup_package(context_id)
                if setup_stdio:
                    self._setup_stdio()

                self.router.register(self.parent, self.stream)
                self.router.register(self.master, self.stream)

                sys.executable, = eval(os.environ.pop('ARGV0'))
                LOG.debug('Connected to %s; my ID is %r, PID is %r',
                          self.parent, context_id, os.getpid())
                LOG.debug('Recovered sys.executable: %r', sys.executable)

                self._dispatch_calls()
                LOG.debug('ExternalContext.main() normal exit')
            except BaseException:
                LOG.exception('ExternalContext.main() crashed')
                raise
        finally:
            self.broker.shutdown()
            self.broker.join()
