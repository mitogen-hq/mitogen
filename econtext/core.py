#!/usr/bin/env python2.5

"""
Python external execution contexts.
"""

import Queue
import cPickle
import cStringIO
import commands
import getpass
import hmac
import imp
import inspect
import logging
import os
import random
import select
import sha
import signal
import socket
import struct
import sys
import textwrap
import threading
import traceback
import types
import zlib


LOG = logging.getLogger('econtext')
IOLOG = logging.getLogger('econtext.io')
RLOG = logging.getLogger('econtext.ctx')

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


def write_all(fd, s):
    written = 0
    while written < len(s):
        rc = os.write(fd, buffer(s, written))
        if not rc:
            raise IOError('short write')
        written += rc
    return written


def CreateChild(*args):
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
    LOG.debug('CreateChild() child %d fd %d, parent %d, args %r',
              pid, parentfp.fileno(), os.getpid(), args)
    return pid, parentfp


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
        self._context.Enqueue(handle, _DEAD)

    def Send(self, data):
        """Send `data` to the remote."""
        IOLOG.debug('%r.Send(%r)', self, data)
        self._context.Enqueue(handle, data)

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

    def find_module(self, fullname, path=None):
        LOG.debug('SlaveModuleImporter.find_module(%r)', fullname)
        try:
            imp.find_module(fullname)
        except ImportError:
            LOG.debug('find_module(%r) returning self', fullname)
            return self

    def load_module(self, fullname):
        LOG.debug('SlaveModuleImporter.load_module(%r)', fullname)
        ret = self._context.EnqueueAwaitReply(GET_MODULE, None, (fullname,))
        if ret is None:
            raise ImportError('Master does not have %r' % (fullname,))

        path, data = ret
        code = compile(zlib.decompress(data), path, 'exec')
        module = imp.new_module(fullname)
        sys.modules[fullname] = module
        eval(code, vars(module), vars(module))
        return module


class MasterModuleResponder(object):
    def __init__(self, context):
        self._context = context
        self._context.AddHandleCB(self.GetModule, handle=GET_MODULE)

    def GetModule(self, data):
        if data == _DEAD:
            return

        reply_to, fullname = data
        LOG.debug('SlaveModuleImporter.GetModule(%r, %r)', reply_to, fullname)
        try:
            module = __import__(fullname)
            source = zlib.compress(inspect.getsource(module))
            self._context.Enqueue(reply_to, (module.__file__, source))
        except Exception, e:
            LOG.exception('While importing %r', fullname)
            self._context.Enqueue(reply_to, None)


class LogHandler(logging.Handler):
    def __init__(self, context):
        logging.Handler.__init__(self)
        self.context = context
        self.local = threading.local()

    def emit(self, rec):
        if rec.name == 'econtext.io' or \
           getattr(self.local, 'in_commit', False):
            return

        self.local.in_commit = True
        try:
            msg = self.format(rec)
            self.context.Enqueue(FORWARD_LOG, (rec.name, rec.levelno, msg))
        finally:
            self.local.in_commit = False


class LogForwarder(object):
    def __init__(self, context):
        self._context = context
        self._context.AddHandleCB(self.ForwardLog, handle=FORWARD_LOG)
        self._log = RLOG.getChild(self._context.name)

    def ForwardLog(self, data):
        if data == _DEAD:
            return

        name, level, s = data
        self._log.log(level, '%s: %s', name, s)


class Side(object):
    def __init__(self, stream, fd):
        self.stream = stream
        self.fd = fd

    def __repr__(self):
        return '<fd %r of %r>' % (self.fd, self.stream)

    def fileno(self):
        return self.fd


class BasicStream(object):
    read_side = None
    write_side = None

    def Disconnect(self):
        LOG.debug('%r: disconnect on %r', self._broker, self)
        self._broker.RemoveStream(self)

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
        if not buf:
            return self.Disconnect()

        self._input_buf += buf
        while len(self._input_buf) >= 24:
            self._ReceiveOne()

    def _ReceiveOne(self):
        msg_mac = self._input_buf[:20]
        msg_len = struct.unpack('>L', self._input_buf[20:24])[0]
        if len(self._input_buf) < msg_len-24:
            IOLOG.debug('Input too short')
            return

        self._rhmac.update(self._input_buf[20:msg_len+24])
        expected_mac = self._rhmac.digest()
        if msg_mac != expected_mac:
            raise CorruptMessageError('%r invalid MAC: expected %r, got %r',
                                      self, msg_mac.encode('hex'),
                                      expected_mac.encode('hex'))

        try:
            handle, data = self.Unpickle(self._input_buf[24:msg_len+24])
        except (TypeError, ValueError), ex:
            raise CorruptMessageError('%r got invalid message: %s', self, ex)

        self._input_buf = self._input_buf[msg_len+24:]
        self._Invoke(handle, data)

    def _Invoke(self, handle, data):
        LOG.debug('%r._Invoke(): handle=%r; data=%r', self, handle, data)
        try:
            persist, fn = self._context._handle_map[handle]
        except KeyError, ex:
            raise CorruptMessageError('%r got invalid handle: %r', self, handle)

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
        LOG.debug('%r.Disconnect()', self)
        if self._context.stream is self:
            self._context.Disconnect()

        try:
            os.close(self.read_side.fd)
        except OSError, e:
            LOG.debug('%r.Disconnect(): did not close fd %s: %s',
                      self, self.read_side.fd, e)

        if self.read_side.fd != self.write_side.fd:
            try:
                os.close(self.write_side.fd)
            except OSError, e:
                LOG.debug('%r.Disconnect(): did not close fd %s: %s',
                          self, self.write_side.fd, e)

        self.read_side.fd = None
        self.write_side.fd = None
        for handle, (persist, fn) in self._context._handle_map.iteritems():
            LOG.debug('%r.Disconnect(): killing %r: %r', self, handle, fn)
            fn(_DEAD)

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


class LocalStream(Stream):
    """
    Base for streams capable of starting new slaves.
    """
    #: The path to the remote Python interpreter.
    python_path = sys.executable

    def __init__(self, context):
        super(LocalStream, self).__init__(context)
        self._permitted_classes = set([('econtext.core', 'CallError')])

    def _FindGlobal(self, module_name, class_name):
        """Return the class implementing `module_name.class_name` or raise
        `StreamError` if the module is not whitelisted."""
        if (module_name, class_name) not in self._permitted_classes:
            raise StreamError('%r attempted to unpickle %r in module %r',
                              self._context, class_name, module_name)
        return getattr(sys.modules[module_name], class_name)

    def AllowClass(self, module_name, class_name):
        """Add `module_name` to the list of permitted modules."""
        self._permitted_modules.add((module_name, class_name))

    # base64'd and passed to 'python -c'. It forks, dups 0->100, creates a
    # pipe, then execs a new interpreter with a custom argv. CONTEXT_NAME is
    # replaced with the context name. Optimized for size.
    def _FirstStage():
        import os,sys,zlib
        R,W=os.pipe()
        if os.fork():
            os.dup2(0,100)
            os.dup2(R,0)
            os.close(R)
            os.close(W)
            os.execv(sys.executable,('econtext:'+CONTEXT_NAME,))
        else:
            os.fdopen(W,'wb',0).write(zlib.decompress(sys.stdin.read(input())))
            print 'OK'
            sys.exit(0)

    def GetBootCommand(self):
        source = inspect.getsource(self._FirstStage)
        source = textwrap.dedent('\n'.join(source.strip().split('\n')[1:]))
        source = source.replace('    ', '\t')
        source = source.replace('CONTEXT_NAME', repr(self._context.name))
        encoded = source.encode('base64').replace('\n', '')
        return [self.python_path, '-c',
                'exec "%s".decode("base64")' % (encoded,)]

    def __repr__(self):
        return '%s(%s)' % (self.__class__.__name__, self._context)

    def Connect(self):
        LOG.debug('%r.Connect()', self)
        pid, sock = CreateChild(*self.GetBootCommand())
        self.read_side = Side(self, os.dup(sock.fileno()))
        self.write_side = self.read_side
        sock.close()
        LOG.debug('%r.Connect(): child process stdin/stdout=%r',
                  self, self.read_side.fd)

        source = inspect.getsource(sys.modules[__name__])
        source += '\nExternalContext().main(%r, %r, %r)\n' % (
            self._context.name,
            self._context.key,
            LOG.level or logging.getLogger().level or logging.INFO,
        )

        compressed = zlib.compress(source)
        preamble = str(len(compressed)) + '\n' + compressed
        write_all(self.write_side.fd, preamble)
        assert os.read(self.read_side.fd, 3) == 'OK\n'


class SSHStream(LocalStream):
    #: The path to the SSH binary.
    ssh_path = 'ssh'

    def GetBootCommand(self):
        bits = [self.ssh_path]
        if self._context.username:
            bits += ['-l', self._context.username]
        bits.append(self._context.hostname)
        base = super(SSHStream, self).GetBootCommand()
        return bits + map(commands.mkarg, base)


class Context(object):
    """
    Represent a remote context regardless of connection method.
    """
    stream = None

    def __init__(self, broker, name=None, hostname=None, username=None,
                 key=None, parent_addr=None, finalize_on_disconnect=False):
        self.broker = broker
        self.name = name
        self.hostname = hostname
        self.username = username
        self.key = key or ('%016x' % random.getrandbits(128))
        self.parent_addr = parent_addr
        self.finalize_on_disconnect = finalize_on_disconnect

        self._last_handle = 1000L
        self._handle_map = {}
        self._lock = threading.Lock()

        self.responder = MasterModuleResponder(self)
        self.log_forwarder = LogForwarder(self)

    def Disconnect(self):
        self.stream = None
        if self.finalize_on_disconnect:
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
        self._stream.Enqueue(handle, obj)

    def EnqueueAwaitReply(self, handle, deadline, data):
        """Send `data` to `handle` and wait for a response with an optional
        timeout. The message contains `(reply_to, data)`, where `reply_to` is
        the handle on which this function expects its reply."""
        reply_to = self.AllocHandle()
        LOG.debug('%r.EnqueueAwaitReply(%r, %r, %r) -> reply handle %d',
                  self, handle, deadline, data, reply_to)

        queue = Queue.Queue()

        def _Receive(data):
            LOG.debug('%r._Receive(%r)', self, data)
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

        LOG.debug('%r._EnqueueAwaitReply(): got reply: %r', self, data)
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
        bits = map(repr, filter(None, [self.name, self.hostname, self.username]))
        return 'Context(%s)' % ', '.join(bits)


class Waker(BasicStream):
    def __init__(self, broker):
        self._broker = broker
        rfd, wfd = os.pipe()
        self.read_side = Side(self, rfd)
        self.write_side = Side(self, wfd)
        broker.UpdateStream(self)

    def __repr__(self):
        return '<Waker>'

    def Wake(self):
        os.write(self.write_side.fd, ' ')

    def Receive(self):
        os.read(self.read_side.fd, 1)


class Listener(BasicStream):
    def __init__(self, broker, address=None, backlog=30):
        self._broker = broker
        self._sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._sock.bind(address or ('0.0.0.0', 0))
        self._sock.listen(backlog)
        self._listen_addr = self._sock.getsockname()
        self.read_side = Side(self, self._sock.fileno())
        broker.UpdateStream(self)

    def Receive(self):
        sock, addr = self._sock.accept()
        context = Context(self._broker, name=addr)
        Stream(context).Accept(sock.fileno(), sock.fileno())


class IoLogger(BasicStream):
    _buf = ''

    def __init__(self, broker, name):
        self._broker = broker
        self._name = name
        self._log = logging.getLogger(name)
        rfd, wfd = os.pipe()

        self.read_side = Side(self, rfd)
        self.write_side = Side(self, wfd)
        self._broker.UpdateStream(self)

    def __repr__(self):
        return '<IoLogger %s fd %d>' % (self._name, self.read_side.fd)

    def _LogLines(self):
        while self._buf.find('\n') != -1:
            line, _, self._buf = self._buf.partition('\n')
            self._log.debug('%s: %s', self._name, line.rstrip('\n'))

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

    def CreateListener(self, address=None, backlog=30):
        """Listen on `address `for connections from newly spawned contexts."""
        self._listener = Listener(self, address, backlog)

    def _UpdateStream(self, stream):
        IOLOG.debug('_UpdateStream(%r)', stream)
        self._lock.acquire()
        try:
            if stream.ReadMore() and stream.read_side.fileno():
                self._readers.add(stream.read_side)
            else:
                self._readers.discard(stream.read_side)

            if stream.WriteMore() and stream.write_side.fileno():
                self._writers.add(stream.write_side)
            else:
                self._writers.discard(stream.write_side)
        finally:
            self._lock.release()

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

    def GetLocal(self, name='default'):
        """Get the named context running on the local machine, creating it if
        it does not exist."""
        context = Context(self, name)
        context.stream = LocalStream(context)
        context.stream.Connect()
        return self.Register(context)

    def GetRemote(self, hostname, username, name=None, python_path=None):
        """Get the named remote context, creating it if it does not exist."""
        if name is None:
            name = 'econtext[%s@%s:%d]' %\
                (username, socket.gethostname(), os.getpid())

        context = Context(self, name, hostname, username)
        context.stream = SSHStream(context)
        if python_path:
            context.stream.python_path = python_path
        context.stream.Connect()
        return self.Register(context)

    def _CallAndUpdate(self, stream, func):
        try:
            func()
        except Exception, e:
            LOG.exception('%r crashed', stream)
            stream.Disconnect()
        self._UpdateStream(stream)

    def _LoopOnce(self):
        IOLOG.debug('%r.Loop()', self)
        #IOLOG.debug('readers = %r', [(r.fileno(), r) for r in self._readers])
        #IOLOG.debug('writers = %r', [(w.fileno(), w) for w in self._writers])
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

            for context in self._contexts.itervalues():
                if context.stream:
                    context.stream.Disconnect()
        except Exception:
            LOG.exception('Loop() crashed')

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
        global core
        sys.modules['econtext'] = sys.modules['__main__']
        sys.modules['econtext.core'] = sys.modules['__main__']
        core = sys.modules['__main__']

        for klass in globals().itervalues():
            if hasattr(klass, '__module__'):
                klass.__module__ = 'econtext.core'

    def _ReapFirstStage(self):
        os.wait()
        os.dup2(100, 0)
        os.close(100)

    def _SetupMaster(self, key):
        self.broker = Broker()
        self.context = Context(self.broker, 'parent', key=key,
                               finalize_on_disconnect=True)
        self.channel = Channel(self.context, CALL_FUNCTION)
        self.context.stream = Stream(self.context)
        self.context.stream.Accept(0, 1)

    def _SetupLogging(self, log_level):
        logging.basicConfig(level=log_level)
        root = logging.getLogger()
        root.setLevel(log_level)
        root.handlers = [LogHandler(self.context)]
        LOG.info('Connected to %s', self.context)

    def _SetupImporter(self):
        self.importer = SlaveModuleImporter(self.context)
        sys.meta_path.append(self.importer)

    def _SetupStdio(self):
        self.stdout_log = IoLogger(self.broker, 'stdout')
        self.stderr_log = IoLogger(self.broker, 'stderr')
        os.dup2(self.stdout_log.write_side.fd, 1)
        os.dup2(self.stderr_log.write_side.fd, 2)

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
                obj = __import__(modname)
                if klass:
                    obj = getattr(obj, klass)
                fn = getattr(obj, func)
                self.context.Enqueue(reply_to, fn(*args, **kwargs))
            except Exception, e:
                self.context.Enqueue(reply_to, CallError(e))

    def main(self, context_name, key, log_level):
        self._ReapFirstStage()
        self._FixupMainModule()
        self._SetupMaster(key)
        self._SetupLogging(log_level)
        self._SetupImporter()
        self._SetupStdio()

        self.broker.Register(self.context)
        self._DispatchCalls()
        self.broker.Wait()
        LOG.debug('ExternalContext.main() exitting')
