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


def write_all(fd, s):
    written = 0
    while written < len(s):
        rc = os.write(fd, buffer(s, written))
        if not rc:
            raise IOError('short write')
        written += rc
    return written


class Channel(object):
    def __init__(self, context, handle):
        self._context = context
        self._handle = handle
        self._queue = Queue.Queue()
        self._context.add_handle_cb(self._receive, handle)

    def _receive(self, data):
        """Callback from the Stream; appends data to the internal queue."""
        IOLOG.debug('%r._receive(%r)', self, data)
        self._queue.put(data)

    def close(self):
        """Indicate this channel is closed to the remote side."""
        IOLOG.debug('%r.close()', self)
        self._context.enqueue(self._handle, _DEAD)

    def send(self, data):
        """Send `data` to the remote."""
        IOLOG.debug('%r.send(%r)', self, data)
        self._context.enqueue(self._handle, data)

    def receive(self, timeout=None):
        """Receive an object, or ``None`` if `timeout` is reached."""
        IOLOG.debug('%r.on_receive(timeout=%r)', self, timeout)
        try:
            data = self._queue.get(True, timeout)
        except Queue.Empty:
            return

        IOLOG.debug('%r.on_receive() got %r', self, data)
        if not isinstance(data, (Dead, CallError)):
            return data
        elif data == _DEAD:
            raise ChannelError('Channel is closed.')
        else:
            raise data

    def __iter__(self):
        """Yield objects from this channel until it is closed."""
        while True:
            try:
                yield self.receive()
            except ChannelError:
                return

    def __repr__(self):
        return 'Channel(%r, %r)' % (self._context, self._handle)


class Importer(object):
    """
    Import protocol implementation that fetches modules from the parent
    process.

    :param context: Context to communicate via.
    """
    def __init__(self, context):
        self._context = context
        self._present = {'econtext': ['econtext.utils', 'econtext.master']}
        self.tls = threading.local()

    def __repr__(self):
        return 'Importer()'

    def find_module(self, fullname, path=None):
        if hasattr(self.tls, 'running'):
            return None

        self.tls.running = True
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
        ret = self._context.enqueue_await_reply(GET_MODULE, None, (fullname,))
        if ret is None:
            raise ImportError('Master does not have %r' % (fullname,))

        is_pkg, present, path, data = ret
        mod = sys.modules.setdefault(fullname, imp.new_module(fullname))
        mod.__loader__ = self
        if is_pkg:
            mod.__path__ = []
            mod.__package__ = fullname
            self._present[fullname] = present
        else:
            mod.__package__ = fullname.rpartition('.')[0]
        code = compile(zlib.decompress(data), 'master:' + path, 'exec')
        exec code in vars(mod)
        return mod


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
            self.context.enqueue(FORWARD_LOG, (rec.name, rec.levelno, msg))
        finally:
            self.local.in_emit = False


class Side(object):
    """
    Represent a single side of a :py:class:`BasicStream`. This exists to allow
    streams implemented using unidirectional (e.g. UNIX pipe) and bidirectional
    (e.g. UNIX socket) file descriptors to operate identically.
    """
    def __init__(self, stream, fd, keep_alive=False):
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

    def __init__(self, context):
        self._context = context
        self._rhmac = hmac.new(context.key, digestmod=sha)
        self._whmac = self._rhmac.copy()

    _find_global = None

    def unpickle(self, data):
        """Deserialize `data` into an object."""
        IOLOG.debug('%r.unpickle(%r)', self, data)
        fp = cStringIO.StringIO(data)
        unpickler = cPickle.Unpickler(fp)
        if self._find_global:
            unpickler.find_global = self._find_global
        return unpickler.load()

    def on_receive(self, broker):
        """Handle the next complete message on the stream. Raise
        :py:class:`StreamError` on failure."""
        IOLOG.debug('%r.on_receive()', self)

        buf = os.read(self.receive_side.fd, 4096)
        self._input_buf += buf
        while self._receive_one():
            pass

        if not buf:
            return self.on_disconnect(broker)

    def _receive_one(self):
        if len(self._input_buf) < 24:
            return False

        msg_mac = self._input_buf[:20]
        msg_len = struct.unpack('>L', self._input_buf[20:24])[0]
        if len(self._input_buf)-24 < msg_len:
            IOLOG.debug('Input too short')
            return False

        self._rhmac.update(self._input_buf[20:msg_len+24])
        expected_mac = self._rhmac.digest()
        if msg_mac != expected_mac:
            raise StreamError('bad MAC: %r != got %r; %r',
                              msg_mac.encode('hex'),
                              expected_mac.encode('hex'),
                              self._input_buf[24:msg_len+24])

        try:
            handle, data = self.unpickle(self._input_buf[24:msg_len+24])
        except (TypeError, ValueError), ex:
            raise StreamError('invalid message: %s', ex)

        self._input_buf = self._input_buf[msg_len+24:]
        self._invoke(handle, data)
        return True

    def _invoke(self, handle, data):
        IOLOG.debug('%r._invoke(%r, %r)', self, handle, data)
        try:
            persist, fn = self._context._handle_map[handle]
        except KeyError:
            raise StreamError('%r: invalid handle: %r', self, handle)

        if not persist:
            del self._context._handle_map[handle]

        try:
            fn(data)
        except Exception:
            LOG.debug('%r._invoke(%r, %r): %r crashed', self, handle, data, fn)

    def on_transmit(self, broker):
        """Transmit buffered messages."""
        IOLOG.debug('%r.on_transmit()', self)
        written = os.write(self.transmit_side.fd, self._output_buf[:4096])
        self._output_buf = self._output_buf[written:]
        if not self._output_buf:
            broker.stop_transmit(self)

    def _enqueue(self, handle, obj):
        IOLOG.debug('%r._enqueue(%r, %r)', self, handle, obj)
        try:
            encoded = cPickle.dumps((handle, obj), protocol=2)
        except cPickle.PicklingError, e:
            encoded = cPickle.dumps((handle, CallError(e)), protocol=2)

        msg = struct.pack('>L', len(encoded)) + encoded
        self._whmac.update(msg)
        self._output_buf += self._whmac.digest() + msg
        self._context.broker.start_transmit(self)

    def enqueue(self, handle, obj):
        """Enqueue `obj` to `handle`, and tell the broker we have output. May
        be called from any thread."""
        self._context.broker.on_thread(self._enqueue, handle, obj)

    def on_disconnect(self, broker):
        super(Stream, self).on_disconnect(broker)
        if self._context.stream is self:
            self._context.on_disconnect(broker)

    def on_shutdown(self, broker):
        """Override BasicStream behaviour of immediately disconnecting."""
        LOG.debug('%r.on_shutdown(%r)', self, broker)

    def accept(self, rfd, wfd):
        self.receive_side = Side(self, os.dup(rfd))
        self.transmit_side = Side(self, os.dup(wfd))
        set_cloexec(self.receive_side.fd)
        set_cloexec(self.transmit_side.fd)
        self._context.stream = self

    def connect(self):
        """Connect to a Broker at the address specified in our associated
        Context."""
        LOG.debug('%r.connect()', self)
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.receive_side = Side(self, sock.fileno())
        self.transmit_side = Side(self, sock.fileno())
        sock.connect(self._context.parent_addr)
        self.enqueue(0, self._context.name)

    def __repr__(self):
        return '%s(%r)' % (self.__class__.__name__, self._context)


class Context(object):
    """
    Represent a remote context regardless of connection method.
    """
    stream = None
    remote_name = None

    def __init__(self, broker, name=None, hostname=None, username=None,
                 key=None, parent_addr=None):
        self.broker = broker
        self.name = name
        self.hostname = hostname
        self.username = username
        self.key = key or ('%016x' % random.getrandbits(128))
        self.parent_addr = parent_addr
        self._last_handle = itertools.count(1000)
        self._handle_map = {}

    def on_shutdown(self, broker):
        """Called during :py:meth:`Broker.shutdown`, informs callbacks
        registered with :py:meth:`add_handle_cb` the connection is dead."""
        LOG.debug('%r.on_shutdown(%r)', self, broker)
        for handle, (persist, fn) in self._handle_map.iteritems():
            LOG.debug('%r.on_disconnect(): killing %r: %r', self, handle, fn)
            fn(_DEAD)

    def on_disconnect(self, broker):
        self.stream = None
        LOG.debug('Parent stream is gone, dying.')
        broker.shutdown()

    def alloc_handle(self):
        """Allocate a handle."""
        return self._last_handle.next()

    def add_handle_cb(self, fn, handle, persist=True):
        """Invoke `fn(obj)` for each `obj` sent to `handle`. Unregister after
        one invocation if `persist` is ``False``."""
        IOLOG.debug('%r.add_handle_cb(%r, %r, %r)', self, fn, handle, persist)
        self._handle_map[handle] = persist, fn

    def enqueue(self, handle, obj):
        if self.stream:
            self.stream.enqueue(handle, obj)

    def enqueue_await_reply(self, handle, deadline, data):
        """Send `data` to `handle` and wait for a response with an optional
        timeout. The message contains `(reply_to, data)`, where `reply_to` is
        the handle on which this function expects its reply."""
        reply_to = self.alloc_handle()
        LOG.debug('%r.enqueue_await_reply(%r, %r, %r) -> reply handle %d',
                  self, handle, deadline, data, reply_to)

        queue = Queue.Queue()
        self.add_handle_cb(queue.put, reply_to, persist=False)
        self.stream.enqueue(handle, (reply_to,) + data)

        try:
            data = queue.get(True, deadline)
        except Queue.Empty:
            self.broker.on_thread(self.stream.on_disconnect, self.broker)
            raise TimeoutError('deadline exceeded.')

        if data == _DEAD:
            raise StreamError('lost connection during call.')

        IOLOG.debug('%r._enqueue_await_reply(): got reply: %r', self, data)
        return data

    def __repr__(self):
        bits = filter(None, (self.name, self.hostname, self.username))
        return 'Context(%s)' % ', '.join(map(repr, bits))


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
        os.read(self.receive_side.fd, 1)


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

        self.receive_side = Side(self, self._rsock.fileno(), keep_alive=True)
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
        LOG.debug('%r.on_receive()', self)
        buf = os.read(self.receive_side.fd, 4096)
        if not buf:
            return self.on_disconnect(broker)

        self._buf += buf
        self._log_lines()


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
        self._alive = True
        self._queue = Queue.Queue()
        self._contexts = {}
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
        self.on_thread(self._writers.add, stream.transmit_side)

    def stop_transmit(self, stream):
        IOLOG.debug('%r.stop_transmit(%r)', self, stream)
        self.on_thread(self._writers.discard, stream.transmit_side)

    def register(self, context):
        """Register `context` with this broker. Registration simply calls
        :py:meth:`start_receive` on the context's :py:class:`Stream`, and records
        a reference to it so that :py:meth:`Context.on_shutdown` can be
        called during :py:meth:`shutdown`."""
        LOG.debug('%r.register(%r) -> r=%r w=%r', self, context,
                  context.stream.receive_side,
                  context.stream.transmit_side)
        self.start_receive(context.stream)
        self._contexts[context.name] = context
        return context

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
        return any(c.stream and c.name != 'master'
                   for c in self._contexts.itervalues()) or \
               any(side.keep_alive for side in self._readers)

    def _broker_main(self):
        """Handle events until :py:meth:`shutdown`. On shutdown, invoke
        :py:meth:`Stream.on_shutdown` for every active stream, then allow up to
        :py:attr:`shutdown_timeout` seconds for the streams to unregister
        themselves before forcefully calling
        :py:meth:`Stream.on_disconnect`."""
        try:
            while self._alive:
                self._loop_once()

            for side in self._readers | self._writers:
                self._call(side.stream, side.stream.on_shutdown)

            deadline = time.time() + self.shutdown_timeout
            while self.keep_alive() and time.time() < deadline:
                self._loop_once(max(0, deadline - time.time()))

            if self.keep_alive():
                LOG.error('%r: some streams did not close gracefully. '
                          'The most likely cause for this is one or '
                          'more child processes still connected to '
                          'ou stdout/stderr pipes.', self)

            for context in self._contexts.itervalues():
                context.on_shutdown(self)

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
    def _setup_master(self, key):
        self.broker = Broker()
        self.context = Context(self.broker, 'master', key=key)
        self.channel = Channel(self.context, CALL_FUNCTION)
        self.context.stream = Stream(self.context)
        self.context.stream.accept(100, 1)

        os.wait()  # Reap first stage.
        os.close(100)

    def _setup_logging(self, log_level):
        logging.basicConfig(level=log_level)
        root = logging.getLogger()
        root.setLevel(log_level)
        root.handlers = [LogHandler(self.context)]
        LOG.debug('Connected to %s', self.context)

    def _setup_importer(self):
        self.importer = Importer(self.context)
        sys.meta_path.append(self.importer)

    def _setup_package(self):
        econtext = imp.new_module('econtext')
        econtext.__package__ = 'econtext'
        econtext.__path__ = []
        econtext.__loader__ = self.importer
        econtext.slave = True
        econtext.core = sys.modules['__main__']
        del sys.modules['__main__']

        sys.modules['econtext'] = econtext
        sys.modules['econtext.core'] = econtext.core
        for klass in vars(econtext.core).itervalues():
            if hasattr(klass, '__module__'):
                klass.__module__ = 'econtext.core'

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
        for data in self.channel:
            LOG.debug('_dispatch_calls(%r)', data)
            reply_to, with_context, modname, klass, func, args, kwargs = data
            if with_context:
                args = (self,) + args

            try:
                obj = __import__(modname, {}, {}, [''])
                if klass:
                    obj = getattr(obj, klass)
                fn = getattr(obj, func)
                self.context.enqueue(reply_to, fn(*args, **kwargs))
            except Exception, e:
                self.context.enqueue(reply_to, CallError(e))

    def main(self, key, log_level):
        self._setup_master(key)
        try:
            self._setup_logging(log_level)
            self._setup_importer()
            self._setup_package()
            self._setup_stdio()

            self.broker.register(self.context)
            self._dispatch_calls()
            LOG.debug('ExternalContext.main() exitting')
        finally:
            self.broker.shutdown()
            self.broker.join()
