"""
This module implements most package functionality, but remains separate from
non-essential code in order to reduce its size, as it is also implements the
bootstrap code.
"""

import Queue
import cPickle
import cStringIO
import errno
import fcntl
import hmac
import imp
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
import types
import zlib


LOG = logging.getLogger('econtext')
IOLOG = logging.getLogger('econtext.io')

GET_MODULE = 100L
CALL_FUNCTION = 101L
FORWARD_LOG = 102L
SHUTDOWN = 103L


class ContextError(Exception):
    """Raised when a problem occurs with a context."""
    def __init__(self, fmt, *args):
        Exception.__init__(self, fmt % args)


class ChannelError(ContextError):
    """Raised when a channel dies or has been closed."""


class StreamError(ContextError):
    """Raised when a stream cannot be established."""


class CorruptMessageError(StreamError):
    """Raised when a corrupt message is received on a stream."""


class TimeoutError(StreamError):
    """Raised when a timeout occurs on a stream."""


class CallError(ContextError):
    """Raised when .call() fails"""
    def __init__(self, e):
        name = '%s.%s' % (type(e).__module__, type(e).__name__)
        tb = sys.exc_info()[2]
        if tb:
            stack = ''.join(traceback.format_tb(tb))
        else:
            stack = ''
        ContextError.__init__(self, 'call failed: %s: %s\n%s', name, e, stack)


class Dead(object):
    def __eq__(self, other):
        return type(other) is Dead

    def __repr__(self):
        return '<Dead>'


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
        if data == _DEAD:
            raise ChannelError('Channel is closed.')
        return data

    def __iter__(self):
        """Yield objects from this channel until it is closed."""
        while True:
            try:
                yield self.receive()
            except ChannelError:
                return

    def __repr__(self):
        return 'Channel(%r, %r)' % (self._context, self._handle)


class SlaveModuleImporter(object):
    """
    Import protocol implementation that fetches modules from the parent
    process.

    :param context: Context to communicate via.
    """
    def __init__(self, context):
        self._context = context
        self._lock = threading.RLock()
        self._present = {'econtext': ['econtext.utils', 'econtext.master']}
        self._ignore = []

    def find_module(self, fullname, path=None):
        LOG.debug('SlaveModuleImporter.find_module(%r)', fullname)
        if fullname in self._ignore:
            return None

        pkgname, _, _ = fullname.rpartition('.')
        if fullname not in self._present.get(pkgname, (fullname,)):
            LOG.debug('%r: master doesn\'t know %r', self, fullname)
            return None

        self._lock.acquire()
        try:
            self._ignore.append(fullname)
            try:
                __import__(fullname, fromlist=['*'])
            except ImportError:
                LOG.debug('find_module(%r) returning self', fullname)
                return self
        finally:
            self._ignore.pop()
            self._lock.release()

    def load_module(self, fullname):
        LOG.debug('SlaveModuleImporter.load_module(%r)', fullname)
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
    def __init__(self, stream, fd):
        self.stream = stream
        self.fd = fd

    def __repr__(self):
        return '<Side of %r fd %s>' % (self.stream, self.fd)

    def fileno(self):
        if self.fd is None:
            raise StreamError('%r.fileno() called but no FD set', self)
        return self.fd

    def close(self):
        if self.fd is not None:
            IOLOG.debug('%r.close()', self)
            try:
                os.close(self.fd)
            except OSError, e:
                if e.errno != errno.EBADF:
                    LOG.error('%r: close failed', self, e)
            self.fd = None


class BasicStream(object):
    read_side = None
    write_side = None

    def on_disconnect(self):
        """Close our associated descriptors."""
        LOG.debug('%r.on_disconnect()', self)
        self.read_side.close()
        self.write_side.close()

    def on_shutdown(self):
        """Disconnect gracefully. Base implementation calls on_disconnect()."""
        LOG.debug('%r.on_shutdown()', self)
        self.on_disconnect()

    def has_output(self):
        return False


class Stream(BasicStream):
    """
    Initialize a new Stream instance.

    :param context: Context to communicate with.
    """
    _input_buf = ''
    _output_buf = ''

    def __init__(self, context):
        self._context = context
        self._lock = threading.Lock()
        self._rhmac = hmac.new(context.key, digestmod=sha.new)
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

    def on_receive(self):
        """Handle the next complete message on the stream. Raise
        CorruptMessageError or IOError on failure."""
        IOLOG.debug('%r.on_receive()', self)

        buf = os.read(self.read_side.fd, 4096)
        self._input_buf += buf
        while self._receive_one():
            pass

        if not buf:
            return self.on_disconnect()

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
            raise CorruptMessageError('bad MAC: %r != got %r; %r',
                                      msg_mac.encode('hex'),
                                      expected_mac.encode('hex'),
                                      self._input_buf[24:msg_len+24])

        try:
            handle, data = self.unpickle(self._input_buf[24:msg_len+24])
        except (TypeError, ValueError), ex:
            raise CorruptMessageError('invalid message: %s', ex)

        self._input_buf = self._input_buf[msg_len+24:]
        self._invoke(handle, data)
        return True

    def _invoke(self, handle, data):
        IOLOG.debug('%r._invoke(): handle=%r; data=%r', self, handle, data)
        try:
            persist, fn = self._context._handle_map[handle]
        except KeyError:
            raise CorruptMessageError('%r: invalid handle: %r', self, handle)

        if not persist:
            del self._context._handle_map[handle]
        fn(data)

    def on_transmit(self):
        """Transmit buffered messages."""
        IOLOG.debug('%r.on_transmit()', self)
        written = os.write(self.write_side.fd, self._output_buf[:4096])
        self._output_buf = self._output_buf[written:]
        if (not self._output_buf) and not self._context.broker.graceful_count:
            self.on_disconnect()

    def has_output(self):
        return bool(self._output_buf)

    def enqueue(self, handle, obj):
        """Enqueue `obj` to `handle`, and tell the broker we have output."""
        IOLOG.debug('%r.enqueue(%r, %r)', self, handle, obj)
        self._lock.acquire()
        try:
            encoded = cPickle.dumps((handle, obj), protocol=2)
            msg = struct.pack('>L', len(encoded)) + encoded
            self._whmac.update(msg)
            self._output_buf += self._whmac.digest() + msg
        finally:
            self._lock.release()
        self._context.broker.update_stream(self)

    def on_disconnect(self):
        super(Stream, self).on_disconnect()
        if self._context.stream is self:
            self._context.on_disconnect()

        for handle, (persist, fn) in self._context._handle_map.iteritems():
            LOG.debug('%r.on_disconnect(): killing %r: %r', self, handle, fn)
            fn(_DEAD)

    def on_shutdown(self):
        """Override BasicStream behaviour of immediately disconnecting."""

    def accept(self, rfd, wfd):
        self.read_side = Side(self, os.dup(rfd))
        self.write_side = Side(self, os.dup(wfd))
        set_cloexec(self.read_side.fd)
        set_cloexec(self.write_side.fd)
        self._context.stream = self

    def connect(self):
        """Connect to a Broker at the address specified in our associated
        Context."""
        LOG.debug('%r.connect()', self)
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.read_side = Side(self, sock.fileno())
        self.write_side = Side(self, sock.fileno())
        sock.connect(self._context.parent_addr)
        self.enqueue(0, self._context.name)

    def __repr__(self):
        return '%s(<context=%r>)' % (self.__class__.__name__, self._context)


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

        self._last_handle = 1000L
        self._handle_map = {}
        self._lock = threading.Lock()
        self.add_handle_cb(self._shutdown, SHUTDOWN)

    def on_shutdown(self):
        """Slave does nothing, _broker_main() will shutdown its streams."""

    def _shutdown(self, data):
        if data != _DEAD and self.stream:
            LOG.debug('Received SHUTDOWN')
            self.broker.shutdown()

    def on_disconnect(self):
        self.stream = None
        LOG.debug('Parent stream is gone, dying.')
        self.broker.shutdown()

    def alloc_handle(self):
        """Allocate a handle."""
        self._lock.acquire()
        try:
            self._last_handle += 1L
            return self._last_handle
        finally:
            self._lock.release()

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

        def _put_reply(data):
            IOLOG.debug('%r._put_reply(%r)', self, data)
            queue.put(data)

        self.add_handle_cb(_put_reply, reply_to, persist=False)
        self.stream.enqueue(handle, (reply_to,) + data)

        try:
            data = queue.get(True, deadline)
        except Queue.Empty:
            self.stream.on_disconnect()
            raise TimeoutError('deadline exceeded.')

        if data == _DEAD:
            raise StreamError('lost connection during call.')

        IOLOG.debug('%r._enqueue_await_reply(): got reply: %r', self, data)
        return data

    def call_with_deadline(self, deadline, with_context, fn, *args, **kwargs):
        LOG.debug('%r.call_with_deadline(%r, %r, %r, *%r, **%r)',
                  self, deadline, with_context, fn, args, kwargs)

        if isinstance(fn, types.MethodType) and \
           isinstance(fn.im_self, (type, types.ClassType)):
            klass = fn.im_self.__name__
        else:
            klass = None

        call = (with_context, fn.__module__, klass, fn.__name__, args, kwargs)
        result = self.enqueue_await_reply(CALL_FUNCTION, deadline, call)
        if isinstance(result, CallError):
            raise result
        return result

    def call(self, fn, *args, **kwargs):
        return self.call_with_deadline(None, False, fn, *args, **kwargs)

    def __repr__(self):
        bits = filter(None, (self.name, self.hostname, self.username))
        return 'Context(%s)' % ', '.join(map(repr, bits))


class Waker(BasicStream):
    def __init__(self, broker):
        self._broker = broker
        rfd, wfd = os.pipe()
        set_cloexec(rfd)
        set_cloexec(wfd)
        self.read_side = Side(self, rfd)
        self.write_side = Side(self, wfd)
        broker.update_stream(self)

    def __repr__(self):
        return '<Waker>'

    def wake(self):
        if self.write_side.fd:
            os.write(self.write_side.fd, ' ')

    def on_receive(self):
        os.read(self.read_side.fd, 1)


class IoLogger(BasicStream):
    _buf = ''

    def __init__(self, broker, name, dest_fd):
        self._broker = broker
        self._name = name
        self._log = logging.getLogger(name)
        self._rsock, self._wsock = socket.socketpair()

        os.dup2(self._wsock.fileno(), dest_fd)
        set_cloexec(self._rsock.fileno())
        set_cloexec(self._wsock.fileno())

        self.read_side = Side(self, self._rsock.fileno())
        self.write_side = Side(self, dest_fd)
        broker.graceful_count += 1
        self._broker.update_stream(self)

    def __repr__(self):
        return '<IoLogger %s fd %d>' % (self._name, self.read_side.fd)

    def _log_lines(self):
        while self._buf.find('\n') != -1:
            line, _, self._buf = self._buf.partition('\n')
            self._log.info('%s', line.rstrip('\n'))

    def on_shutdown(self):
        LOG.debug('%r.on_shutdown()', self)
        self._wsock.shutdown(socket.SHUT_WR)
        self._wsock.close()

    def on_receive(self):
        LOG.debug('%r.on_receive()', self)
        buf = os.read(self.read_side.fd, 4096)
        if not buf:
            LOG.debug('%r decrement graceful_count', self)
            self._broker.graceful_count -= 1
            return self.on_disconnect()

        self._buf += buf
        self._log_lines()


class Broker(object):
    """
    Broker: responsible for tracking contexts, associated streams, and I/O
    multiplexing.
    """
    _waker = None
    graceful_count = 0
    graceful_timeout = 3.0

    def __init__(self):
        self._alive = True
        self._lock = threading.RLock()
        self._contexts = {}
        self._readers = set()
        self._writers = set()
        self._waker = Waker(self)

        self._thread = threading.Thread(target=self._broker_main,
                                        name='econtext-broker')
        self._thread.start()

    def _update_stream(self, stream):
        IOLOG.debug('_update_stream(%r)', stream)
        self._lock.acquire()
        try:
            if stream.read_side.fd is not None:
                self._readers.add(stream.read_side)
            else:
                self._readers.discard(stream.read_side)

            if stream.write_side.fd is not None and stream.has_output():
                self._writers.add(stream.write_side)
            else:
                self._writers.discard(stream.write_side)
        finally:
            self._lock.release()

    def update_stream(self, stream):
        self._update_stream(stream)
        if self._waker:
            self._waker.wake()

    def register(self, context):
        """Put a context under control of this broker."""
        LOG.debug('%r.register(%r) -> r=%r w=%r', self, context,
                  context.stream.read_side,
                  context.stream.write_side)
        self.update_stream(context.stream)
        self._contexts[context.name] = context
        return context

    def _call_and_update(self, stream, func):
        try:
            func()
        except Exception:
            LOG.exception('%r crashed', stream)
            stream.on_disconnect()
        self._update_stream(stream)

    def _loop_once(self, timeout=None):
        IOLOG.debug('%r._loop_once(%r)', self, timeout)
        #IOLOG.debug('readers = %r', [(r.fileno(), r) for r in self._readers])
        #IOLOG.debug('writers = %r', [(w.fileno(), w) for w in self._writers])
        rsides, wsides, _ = select.select(self._readers, self._writers,
                                          (), timeout)
        for side in rsides:
            IOLOG.debug('%r: POLLIN for %r', self, side.stream)
            self._call_and_update(side.stream, side.stream.on_receive)

        for side in wsides:
            IOLOG.debug('%r: POLLOUT for %r', self, side.stream)
            self._call_and_update(side.stream, side.stream.on_transmit)

    def _broker_main(self):
        """Handle events until shutdown()."""
        try:
            while self._alive:
                self._loop_once()

            for side in self._readers | self._writers:
                self._call_and_update(side.stream, side.stream.on_shutdown)

            deadline = time.time() + self.graceful_timeout
            while ((self._readers or self._writers) and
                   (self.graceful_count or time.time() < deadline)):
                self._loop_once(1.0)

            for context in self._contexts.itervalues():
                stream = context.stream
                if stream:
                    stream.on_disconnect()
                    self._update_stream(stream)

            for side in self._readers | self._writers:
                LOG.error('_broker_main() force disconnecting %r', side)
                side.stream.on_disconnect()
        except Exception:
            LOG.exception('_broker_main() crashed')

    def shutdown(self):
        """Request broker gracefully disconnect streams and stop."""
        LOG.debug('%r.shutdown()', self)
        self._alive = False
        self._waker.wake()

    def wait(self):
        """Wait for the broker to stop."""
        self._thread.join()

    def __repr__(self):
        return 'Broker()'


class ExternalContext(object):
    def _setup_package(self):
        econtext = imp.new_module('econtext')
        econtext.__package__ = 'econtext'
        econtext.__path__ = []
        econtext.core = sys.modules['__main__']

        sys.modules['econtext'] = econtext
        sys.modules['econtext.core'] = econtext.core
        exec 'from econtext.core import *' in vars(econtext)

        for klass in vars(econtext.core).itervalues():
            if hasattr(klass, '__module__'):
                klass.__module__ = 'econtext.core'

    def _setup_master(self, key):
        os.wait()  # Reap first stage.

        self.broker = Broker()
        self.context = Context(self.broker, 'master', key=key)
        self.channel = Channel(self.context, CALL_FUNCTION)
        self.context.stream = Stream(self.context)
        self.context.stream.accept(100, 1)
        os.close(100)

    def _setup_logging(self, log_level):
        logging.basicConfig(level=log_level)
        root = logging.getLogger()
        root.setLevel(log_level)
        root.handlers = [LogHandler(self.context)]
        LOG.debug('Connected to %s', self.context)

    def _setup_importer(self):
        self.importer = SlaveModuleImporter(self.context)
        sys.meta_path.append(self.importer)

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
                obj = __import__(modname, fromlist=['*'])
                if klass:
                    obj = getattr(obj, klass)
                fn = getattr(obj, func)
                self.context.enqueue(reply_to, fn(*args, **kwargs))
            except Exception, e:
                self.context.enqueue(reply_to, CallError(e))

    def main(self, key, log_level):
        self._setup_package()
        self._setup_master(key)
        try:
            self._setup_logging(log_level)
            self._setup_importer()
            self._setup_stdio()

            self.broker.register(self.context)
            self._dispatch_calls()
            LOG.debug('ExternalContext.main() exitting')
        finally:
            self.broker.shutdown()
            self.broker.wait()
