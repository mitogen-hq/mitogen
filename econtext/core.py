"""
Python external execution contexts.
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
    """Raised when .Call() fails"""
    def __init__(self, e):
        name = '%s.%s' % (type(e).__module__, type(e).__name__)
        tb = sys.exc_info()[2]
        if tb:
            stack = ''.join(traceback.format_tb(tb))
        else:
            stack = ''
        ContextError.__init__(self, 'Call failed: %s: %s\n%s', name, e, stack)


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
        self._context.AddHandleCB(self._Receive, handle)

    def _Receive(self, data):
        """Callback from the Stream; appends data to the internal queue."""
        IOLOG.debug('%r._Receive(%r)', self, data)
        self._queue.put(data)

    def Close(self):
        """Indicate this channel is closed to the remote side."""
        IOLOG.debug('%r.Close()', self)
        self._context.Enqueue(self._handle, _DEAD)

    def Send(self, data):
        """Send `data` to the remote."""
        IOLOG.debug('%r.Send(%r)', self, data)
        self._context.Enqueue(self._handle, data)

    def Receive(self, timeout=None):
        """Receive an object from the remote, or return ``None`` if `timeout`
        is reached."""
        IOLOG.debug('%r.Receive(timeout=%r)', self, timeout)
        try:
            data = self._queue.get(True, timeout)
        except Queue.Empty:
            return

        IOLOG.debug('%r.Receive() got %r', self, data)
        if data == _DEAD:
            raise ChannelError('Channel is closed.')
        return data

    def __iter__(self):
        """Iterate objects arriving on this channel, until the channel dies or
        is closed."""
        while True:
            try:
                yield self.Receive()
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
            LOG.debug('%r: Skip %r since master doesnt know it', self, fullname)
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
        ret = self._context.EnqueueAwaitReply(GET_MODULE, None, (fullname,))
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
        exec code in mod.__dict__
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
            self.context.Enqueue(FORWARD_LOG, (rec.name, rec.levelno, msg))
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
            try:
                os.close(self.fd)
            except OSError, e:
                if e.errno != errno.EBADF:
                    LOG.error('%r: close failed', self, e)
            self.fd = None


class BasicStream(object):
    read_side = None
    write_side = None

    def Disconnect(self):
        LOG.debug('%r.Disconnect()', self)
        self.read_side.close()
        self.write_side.close()

    def Shutdown(self):
        self.read_side.close()
        self.write_side.close()

    def ReadMore(self):
        return True

    def WriteMore(self):
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

    _FindGlobal = None

    def Unpickle(self, data):
        """Deserialize `data` into an object."""
        IOLOG.debug('%r.Unpickle(%r)', self, data)
        fp = cStringIO.StringIO(data)
        unpickler = cPickle.Unpickler(fp)
        if self._FindGlobal:
            unpickler.find_global = self._FindGlobal
        return unpickler.load()

    def Receive(self):
        """Handle the next complete message on the stream. Raise
        CorruptMessageError or IOError on failure."""
        IOLOG.debug('%r.Receive()', self)

        buf = os.read(self.read_side.fd, 4096)
        self._input_buf += buf
        while self._ReceiveOne():
            pass

        if not buf:
            return self.Disconnect()

    def _ReceiveOne(self):
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
            raise CorruptMessageError('%r bad MAC: %r != got %r; %r',
                                      self, msg_mac.encode('hex'),
                                      expected_mac.encode('hex'),
                                      self._input_buf[24:msg_len+24])

        try:
            handle, data = self.Unpickle(self._input_buf[24:msg_len+24])
        except (TypeError, ValueError), ex:
            raise CorruptMessageError('%r got invalid message: %s', self, ex)

        self._input_buf = self._input_buf[msg_len+24:]
        self._Invoke(handle, data)
        return True

    def _Invoke(self, handle, data):
        IOLOG.debug('%r._Invoke(): handle=%r; data=%r', self, handle, data)
        try:
            persist, fn = self._context._handle_map[handle]
        except KeyError:
            raise CorruptMessageError('%r: invalid handle: %r', self, handle)

        if not persist:
            del self._context._handle_map[handle]
        fn(data)

    def Transmit(self):
        """Transmit buffered messages."""
        IOLOG.debug('%r.Transmit()', self)
        written = os.write(self.write_side.fd, self._output_buf[:4096])
        self._output_buf = self._output_buf[written:]

    def WriteMore(self):
        return bool(self._output_buf)

    def Enqueue(self, handle, obj):
        """Enqueue `obj` to `handle`, and tell the broker we have output."""
        IOLOG.debug('%r.Enqueue(%r, %r)', self, handle, obj)
        self._lock.acquire()
        try:
            encoded = cPickle.dumps((handle, obj), protocol=2)
            msg = struct.pack('>L', len(encoded)) + encoded
            self._whmac.update(msg)
            self._output_buf += self._whmac.digest() + msg
        finally:
            self._lock.release()
        self._context.broker.UpdateStream(self)

    def Disconnect(self):
        """Close our associated file descriptor and tell registered callbacks
        the connection has been destroyed."""
        super(Stream, self).Disconnect()
        if self._context.stream is self:
            self._context.Disconnect()

        for handle, (persist, fn) in self._context._handle_map.iteritems():
            LOG.debug('%r.Disconnect(): killing %r: %r', self, handle, fn)
            fn(_DEAD)

    def Shutdown(self):
        LOG.debug('%r.Shutdown()', self)
        # Cannot use .shutdown() since it may be a pipe.
        self.write_side.close()

    def Accept(self, rfd, wfd):
        self.read_side = Side(self, os.dup(rfd))
        self.write_side = Side(self, os.dup(wfd))
        self._context.stream = self

    def Connect(self):
        """Connect to a Broker at the address specified in our associated
        Context."""
        LOG.debug('%r.Connect()', self)
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.read_side = Side(self, sock.fileno())
        self.write_side = Side(self, sock.fileno())
        sock.connect(self._context.parent_addr)
        self.Enqueue(0, self._context.name)

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

    def Disconnect(self):
        self.stream = None
        LOG.debug('Parent stream is gone, dying.')
        self.broker.Finalize(wait=False)

    def AllocHandle(self):
        """Allocate a handle."""
        self._lock.acquire()
        try:
            self._last_handle += 1L
            return self._last_handle
        finally:
            self._lock.release()

    def AddHandleCB(self, fn, handle, persist=True):
        """Register `fn(obj)` to run for each `obj` sent to `handle`. If
        `persist` is ``False`` then unregister after one delivery."""
        IOLOG.debug('%r.AddHandleCB(%r, %r, persist=%r)',
                    self, fn, handle, persist)
        self._handle_map[handle] = persist, fn

    def Enqueue(self, handle, obj):
        if self.stream:
            self.stream.Enqueue(handle, obj)

    def EnqueueAwaitReply(self, handle, deadline, data):
        """Send `data` to `handle` and wait for a response with an optional
        timeout. The message contains `(reply_to, data)`, where `reply_to` is
        the handle on which this function expects its reply."""
        reply_to = self.AllocHandle()
        LOG.debug('%r.EnqueueAwaitReply(%r, %r, %r) -> reply handle %d',
                  self, handle, deadline, data, reply_to)

        queue = Queue.Queue()

        def _Receive(data):
            IOLOG.debug('%r._Receive(%r)', self, data)
            queue.put(data)

        self.AddHandleCB(_Receive, reply_to, persist=False)
        self.stream.Enqueue(handle, (reply_to,) + data)

        try:
            data = queue.get(True, deadline)
        except Queue.Empty:
            self.stream.Disconnect()
            raise TimeoutError('deadline exceeded.')

        if data == _DEAD:
            raise StreamError('lost connection during call.')

        IOLOG.debug('%r._EnqueueAwaitReply(): got reply: %r', self, data)
        return data

    def CallWithDeadline(self, deadline, with_context, fn, *args, **kwargs):
        LOG.debug('%r.CallWithDeadline(%r, %r, %r, *%r, **%r)',
                  self, deadline, with_context, fn, args, kwargs)

        if isinstance(fn, types.MethodType) and \
           isinstance(fn.im_self, (type, types.ClassType)):
            klass = fn.im_self.__name__
        else:
            klass = None

        call = (with_context, fn.__module__, klass, fn.__name__, args, kwargs)
        result = self.EnqueueAwaitReply(CALL_FUNCTION, deadline, call)
        if isinstance(result, CallError):
            raise result
        return result

    def Call(self, fn, *args, **kwargs):
        return self.CallWithDeadline(None, False, fn, *args, **kwargs)

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
        broker.UpdateStream(self)

    def __repr__(self):
        return '<Waker>'

    def Wake(self):
        os.write(self.write_side.fd, ' ')

    def Receive(self):
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
        self._broker.UpdateStream(self)

    def __repr__(self):
        return '<IoLogger %s fd %d>' % (self._name, self.read_side.fd)

    def _LogLines(self):
        while self._buf.find('\n') != -1:
            line, _, self._buf = self._buf.partition('\n')
            self._log.info('%s', line.rstrip('\n'))

    def Shutdown(self):
        LOG.debug('%r.Shutdown()', self)
        self._wsock.shutdown(2)
        self._wsock.close()

    def Receive(self):
        LOG.debug('%r.Receive()', self)
        buf = os.read(self.read_side.fd, 4096)
        if not buf:
            return self.Disconnect()

        self._buf += buf
        self._LogLines()


class Broker(object):
    """
    Context broker: this is responsible for keeping track of contexts, any
    stream that is associated with them, and for I/O multiplexing.
    """
    _waker = None

    def __init__(self):
        self._alive = True
        self._lock = threading.Lock()
        self._contexts = {}
        self._readers = set()
        self._writers = set()
        self._waker = Waker(self)

        self._thread = threading.Thread(target=self._BrokerMain,
                                        name='econtext-broker')
        self._thread.start()

    def _UpdateStream(self, stream):
        IOLOG.debug('_UpdateStream(%r)', stream)
        self._lock.acquire()
        try:
            if stream.read_side.fd is not None and stream.ReadMore():
                self._readers.add(stream.read_side)
            else:
                self._readers.discard(stream.read_side)

            if stream.write_side.fd is not None and stream.WriteMore():
                self._writers.add(stream.write_side)
            else:
                self._writers.discard(stream.write_side)
        finally:
            self._lock.release()

    def RemoveStream(self, stream):
        self._writers.discard(stream.write_side)
        self._readers.discard(stream.read_side)
        if self._waker:
            self._waker.Wake()

    def UpdateStream(self, stream):
        self._UpdateStream(stream)
        if self._waker:
            self._waker.Wake()

    def Register(self, context):
        """Put a context under control of this broker."""
        LOG.debug('%r.Register(%r) -> r=%r w=%r', self, context,
                  context.stream.read_side,
                  context.stream.write_side)
        self.UpdateStream(context.stream)
        self._contexts[context.name] = context
        return context

    def _CallAndUpdate(self, stream, func):
        try:
            func()
        except Exception:
            LOG.exception('%r crashed', stream)
            stream.Disconnect()
        self._UpdateStream(stream)

    def _LoopOnce(self):
        IOLOG.debug('%r.Loop()', self)
        # IOLOG.debug('readers = %r', [(r.fileno(), r) for r in self._readers])
        # IOLOG.debug('writers = %r', [(w.fileno(), w) for w in self._writers])
        rsides, wsides, _ = select.select(self._readers, self._writers, ())
        for side in rsides:
            IOLOG.debug('%r: POLLIN for %r', self, side.stream)
            self._CallAndUpdate(side.stream, side.stream.Receive)

        for side in wsides:
            IOLOG.debug('%r: POLLOUT for %r', self, side.stream)
            self._CallAndUpdate(side.stream, side.stream.Transmit)

    def _BrokerMain(self):
        """Handle events until Finalize() is called."""
        try:
            while self._alive:
                self._LoopOnce()

            for side in self._readers | self._writers:
                self._CallAndUpdate(side.stream, side.stream.Shutdown)

            deadline = time.time() + 1.0
            while (self._readers or self._writers) and time.time() < deadline:
                LOG.error('%s', [self._readers, self._writers])
                self._LoopOnce()

            for side in self._readers | self._writers:
                LOG.error('_BrokerMain() force disconnecting %r', side.stream)
                side.stream.Disconnect()
        except Exception:
            LOG.exception('_BrokerMain() crashed')

    def Wait(self):
        """Wait for the broker to stop."""
        self._thread.join()

    def Finalize(self, wait=True):
        """Disconect all streams and wait for broker to stop."""
        self._alive = False
        self._waker.Wake()
        if wait:
            self.Wait()

    def __repr__(self):
        return 'Broker()'


class ExternalContext(object):
    def _FixupMainModule(self):
        main = sys.modules['__main__']
        main.__path__ = []
        main.core = main

        sys.modules['econtext'] = main
        sys.modules['econtext.core'] = main
        for klass in globals().itervalues():
            if hasattr(klass, '__module__'):
                klass.__module__ = 'econtext.core'

    def _ReapFirstStage(self):
        os.wait()
        os.dup2(100, 0)
        os.close(100)

    def _SetupMaster(self, key):
        self.broker = Broker()
        self.context = Context(self.broker, 'parent', key=key)
        self.channel = Channel(self.context, CALL_FUNCTION)
        self.context.stream = Stream(self.context)
        self.context.stream.Accept(0, 1)

    def _SetupLogging(self, log_level):
        logging.basicConfig(level=log_level)
        root = logging.getLogger()
        root.setLevel(log_level)
        root.handlers = [LogHandler(self.context)]
        LOG.debug('Connected to %s', self.context)

    def _SetupImporter(self):
        self.importer = SlaveModuleImporter(self.context)
        sys.meta_path.append(self.importer)

    def _SetupStdio(self):
        self.stdout_log = IoLogger(self.broker, 'stdout', 1)
        self.stderr_log = IoLogger(self.broker, 'stderr', 2)
        # Reopen with line buffering.
        sys.stdout = file('/dev/stdout', 'w', 1)

        fp = file('/dev/null')
        try:
            os.dup2(fp.fileno(), 0)
        finally:
            fp.close()

    def _DispatchCalls(self):
        for data in self.channel:
            LOG.debug('_DispatchCalls(%r)', data)
            reply_to, with_context, modname, klass, func, args, kwargs = data
            if with_context:
                args = (self,) + args

            try:
                obj = __import__(modname, fromlist=['*'])
                if klass:
                    obj = getattr(obj, klass)
                fn = getattr(obj, func)
                self.context.Enqueue(reply_to, fn(*args, **kwargs))
            except Exception, e:
                self.context.Enqueue(reply_to, CallError(e))

    def main(self, key, log_level):
        self._ReapFirstStage()
        self._FixupMainModule()
        self._SetupMaster(key)
        self._SetupLogging(log_level)
        self._SetupImporter()
        self._SetupStdio()

        # signal.signal(signal.SIGINT, lambda *_: self.broker.Finalize())
        self.broker.Register(self.context)

        self._DispatchCalls()
        self.broker.Wait()
        LOG.debug('ExternalContext.main() exitting')
