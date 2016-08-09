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
import syslog
import textwrap
import threading
import traceback
import types
import zlib


#
# Module-level data.
#

LOG = logging.getLogger('econtext')

GET_MODULE = 100L
CALL_FUNCTION = 101L
FORWARD_LOG = 102L


#
# Exceptions.
#

class ContextError(Exception):
    'Raised when a problem occurs with a context.'
    def __init__(self, fmt, *args):
        Exception.__init__(self, fmt % args)

class ChannelError(ContextError):
    'Raised when a channel dies or has been closed.'

class StreamError(ContextError):
    'Raised when a stream cannot be established.'

class CorruptMessageError(StreamError):
    'Raised when a corrupt message is received on a stream.'

class TimeoutError(StreamError):
    'Raised when a timeout occurs on a stream.'


#
# Helpers.
#

def write_all(fd, s):
    written = 0
    while written < len(s):
        rc = os.write(fd, buffer(s, written))
        if not rc:
            raise IOError('short write')
        written += rc
    return written


def CreateChild(*args):
    """
    Create a child process whose stdin/stdout is connected to a socket,
    returning `(pid, socket_obj)`.
    """
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


class Formatter(logging.Formatter):
    FMT = '%(asctime)s %(levelname).1s %(name)s: %(message)s'
    DATEFMT = '%H:%M:%S'

    def __init__(self, parent):
        self.parent = parent
        super(Formatter, self).__init__(self.FMT, self.DATEFMT)

    def format(self, record):
        s = super(Formatter, self).format(record)
        if 1:
            p = ''
        elif self.parent:
            p = '\x1b[32m'
        else:
            p = '\x1b[36m'
        return p + ('{%s} %s' % (os.getpid(), s))


class Channel(object):
    def __init__(self, stream, handle):
        self._context = stream._context
        self._stream = stream
        self._handle = handle
        self._queue = Queue.Queue()
        self._context.AddHandleCB(self._InternalReceive, handle)

    def _InternalReceive(self, killed, data):
        """
        Callback from the stream object; appends a tuple of
        (killed-or-closed, data) to the internal queue and wakes the internal
        event.

        Args:
            # Has the Stream object lost its connection?
            killed: bool
            data: (
                # Has the remote Channel had Close() called?
                bool,
                # The object passed to the remote Send()
                object
            )
        """
        LOG.debug('%r._InternalReceive(%r, %r)', self, killed, data)
        self._queue.put((killed or data[0], killed or data[1]))

    def Close(self):
        """
        Indicate this channel is closed to the remote side.
        """
        LOG.debug('%r.Close()', self)
        self._stream.Enqueue(handle, (True, None))

    def Send(self, data):
        """
        Send `data` to the remote.
        """
        LOG.debug('%r.Send(%r)', self, data)
        self._stream.Enqueue(handle, (False, data))

    def Receive(self, timeout=None):
        """
        Receive an object from the remote, or return ``None`` if `timeout` is
        reached.
        """
        LOG.debug('%r.Receive(%r)', self, timeout)
        try:
            killed, data = self._queue.get(True, timeout)
        except Queue.Empty:
            return

        LOG.debug('%r.Receive() got killed=%r, data=%r', self, killed, data)
        if killed:
            raise ChannelError('Channel is closed.')
        return data

    def __iter__(self):
        """
        Return an iterator that yields objects arriving on this channel, until
        the channel dies or is closed.
        """
        while True:
            try:
                yield self.Receive()
            except ChannelError:
                return

    def __repr__(self):
        return 'econtext.Channel(%r, %r)' % (self._stream, self._handle)


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

        kind, path, data = ret
        code = compile(zlib.decompress(data), path, 'exec')
        module = imp.new_module(fullname)
        sys.modules[fullname] = module
        eval(code, vars(module), vars(module))
        return module


class MasterModuleResponder(object):
    def __init__(self, context):
        self._context = context

    def GetModule(self, killed, data):
        if killed:
            return

        _, (reply_to, fullname) = data
        LOG.debug('SlaveModuleImporter.GetModule(%r, %r)', killed, fullname)
        mod = sys.modules.get(fullname)
        if mod:
            source = zlib.compress(inspect.getsource(mod))
            path = os.path.abspath(mod.__file__)
            self._context.Enqueue(reply_to, ('source', path, source))


class LogForwarder(object):
    def __init__(self, context):
        self._context = context

    def ForwardLog(self, killed, data):
        if killed:
            return

        _, (s,) = data
        LOG.debug('%r: %s', self._context, s)


#
# Stream implementations.
#


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

        self._pickler_file = cStringIO.StringIO()
        self._pickler = cPickle.Pickler(self._pickler_file, protocol=2)

        self._unpickler_file = cStringIO.StringIO()
        self._unpickler = cPickle.Unpickler(self._unpickler_file)

    def Pickle(self, obj):
        """
        Serialize `obj` using the pickler.
        """
        self._pickler.dump(obj)
        data = self._pickler_file.getvalue()
        self._pickler_file.seek(0)
        self._pickler_file.truncate(0)
        return data

    def Unpickle(self, data):
        """
        Unserialize `data` into an object using the unpickler.
        """
        LOG.debug('%r.Unpickle(%r)', self, data)
        self._unpickler_file.write(data)
        self._unpickler_file.seek(0)
        data = self._unpickler.load()
        self._unpickler_file.seek(0)
        self._unpickler_file.truncate(0)
        return data

    def Receive(self):
        """
        Handle the next complete message on the stream. Raise
        CorruptMessageError or IOError on failure.
        """
        LOG.debug('%r.Receive()', self)

        buf = os.read(self.read_side.fd, 4096)
        if not buf:
            return self.Disconnect()

        self._input_buf += buf
        if len(self._input_buf) < 24:
            return

        msg_mac = self._input_buf[:20]
        msg_len = struct.unpack('>L', self._input_buf[20:24])[0]
        if len(self._input_buf) < msg_len-24:
            LOG.debug('Input too short')
            return

        self._rhmac.update(self._input_buf[20:msg_len+24])
        expected_mac = self._rhmac.digest()
        if msg_mac != expected_mac:
            raise CorruptMessageError('%r got invalid MAC: expected %r, got %r',
                                      self, msg_mac.encode('hex'),
                                      expected_mac.encode('hex'))

        try:
            handle, data = self.Unpickle(self._input_buf[24:msg_len+24])
            self._input_buf = self._input_buf[msg_len+24:]
            handle = long(handle)

            LOG.debug('%r.Receive(): decoded handle=%r; data=%r',
                      self, handle, data)
            persist, fn = self._context._handle_map[handle]
            if not persist:
                del self._context._handle_map[handle]
        except KeyError, ex:
            raise CorruptMessageError('%r got invalid handle: %r', self, handle)
        except (TypeError, ValueError), ex:
            raise CorruptMessageError('%r got invalid message: %s', self, ex)

        LOG.debug('Calling %r (%r, %r)', fn, False, data)
        fn(False, data)

    def Transmit(self):
        """
        Transmit buffered messages.
        """
        LOG.debug('%r.Transmit()', self)
        written = os.write(self.write_side.fd, self._output_buf[:4096])
        self._output_buf = self._output_buf[written:]

    def WriteMore(self):
        return bool(self._output_buf)

    def Enqueue(self, handle, obj):
        """
        Enqueue `obj` to `handle`, and tell the broker we have output.
        """
        LOG.debug('%r.Enqueue(%r, %r)', self, handle, obj)
        encoded = self.Pickle((handle, obj))
        msg = struct.pack('>L', len(encoded)) + encoded

        self._lock.acquire()
        try:
            self._whmac.update(msg)
            self._output_buf += self._whmac.digest() + msg
        finally:
            self._lock.release()
        self._context.broker.UpdateStream(self)

    def Disconnect(self):
        """
        Close our associated file descriptor and tell registered callbacks the
        connection has been destroyed.
        """
        LOG.debug('%r.Disconnect()', self)
        if self._context.GetStream() is self:
            self._context.SetStream(None)

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
            fn(True, None)

    def Accept(self, rfd, wfd):
        self.read_side = Side(self, os.dup(rfd))
        self.write_side = Side(self, os.dup(wfd))
        self._context.SetStream(self)
        self._context.broker.Register(self._context)

    def Connect(self):
        """
        Connect to a Broker at the address specified in our associated Context.
        """
        LOG.debug('%r.Connect()', self)
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.read_side = Side(self, sock.fileno())
        self.write_side = Side(self, sock.fileno())
        sock.connect(self._context.parent_addr)
        self.Enqueue(0, self._context.name)

    def __repr__(self):
        return 'econtext.%s(<context=%r>)' %\
                     (self.__class__.__name__, self._context)


class LocalStream(Stream):
    """
    Base for streams capable of starting new slaves.
    """
    python_path = property(
        lambda self: getattr(self, '_python_path', sys.executable),
        lambda self, path: setattr(self, '_python_path', path),
        doc='The path to the remote Python interpreter.')

    def __init__(self, context):
        super(LocalStream, self).__init__(context)
        self._permitted_modules = set(['exceptions'])
        self._unpickler.find_global = self._FindGlobal

    def _FindGlobal(self, module_name, class_name):
        """
        Return the class implementing `module_name.class_name` or raise
        `StreamError` if the module is not whitelisted.
        """
        if module_name not in self._permitted_modules:
            raise StreamError('context %r attempted to unpickle %r in module %r',
                              self._context, class_name, module_name)
        return getattr(sys.modules[module_name], class_name)

    def AllowModule(self, module_name):
        """
        Add `module_name` to the list of permitted modules.
        """
        self._permitted_modules.add(module_name)

    # Hexed and passed to 'python -c'. It forks, dups 0->100, creates a pipe,
    # then execs a new interpreter with a custom argv. CONTEXT_NAME is replaced
    # with the context name. Optimized for size.
    def _FirstStage():
        import os,sys,zlib
        R,W=os.pipe()
        if os.fork():
            os.dup2(0,100)
            os.dup2(R,0)
            os.close(R)
            os.close(W)
            os.execv(sys.executable,(CONTEXT_NAME,))
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
        source += '\nExternalContextMain(%r, %r, %r)\n' % (
            self._context.name,
            self._context.broker._listener._listen_addr,
            self._context.key
        )
        compressed = zlib.compress(source)

        preamble = str(len(compressed)) + '\n' + compressed
        write_all(self.write_side.fd, preamble)
        assert os.read(self.read_side.fd, 3) == 'OK\n'


class SSHStream(LocalStream):
    ssh_path = property(
        lambda self: getattr(self, '_ssh_path', 'ssh'),
        lambda self, path: setattr(self, '_ssh_path', path),
        doc='The path to the SSH binary.')

    def GetBootCommand(self):
        bits = [self.ssh_path]
        if self._context.username:
            bits += ['-l', self._context.username]
        bits.append(self._context.hostname)
        base = super(SSHStream, self).GetBootCommand()
        return bits + map(commands.mkarg, base)


class Context(object):
    """
    Represents a remote context regardless of connection method.
    """

    def __init__(self, broker, name=None, hostname=None, username=None, key=None,
                 parent_addr=None):
        self.broker = broker
        self.name = name
        self.hostname = hostname
        self.username = username
        self.parent_addr = parent_addr
        self.key = key or ('%016x' % random.getrandbits(128))

        self._last_handle = 1000L
        self._handle_map = {}
        self._lock = threading.Lock()

        self.responder = MasterModuleResponder(self)
        self.AddHandleCB(self.responder.GetModule, handle=GET_MODULE)

        self.log_forwarder = LogForwarder(self)
        self.AddHandleCB(self.log_forwarder.ForwardLog, handle=FORWARD_LOG)

    def GetStream(self):
        return self._stream

    def SetStream(self, stream):
        self._stream = stream
        return stream

    def AllocHandle(self):
        """
        Allocate a unique handle for this stream.

        Returns:
            long
        """
        self._lock.acquire()
        try:
            self._last_handle += 1L
            return self._last_handle
        finally:
            self._lock.release()

    def AddHandleCB(self, fn, handle, persist=True):
        """
        Register `fn(killed, obj)` to run for each `obj` sent to `handle`. If
        `persist` is ``False`` then unregister after one delivery.
        """
        LOG.debug('%r.AddHandleCB(%r, %r, persist=%r)',
                   self, fn, handle, persist)
        self._handle_map[handle] = persist, fn

    def Enqueue(self, handle, obj):
        self._stream.Enqueue(handle, obj)

    def EnqueueAwaitReply(self, handle, deadline, data):
        """
        Send `data` to `handle` and wait for a response with an optional
        timeout. The message contains `(reply_to, data)`, where `reply_to` is
        the handle on which this function expects its reply.
        """
        reply_to = self.AllocHandle()
        LOG.debug('%r.EnqueueAwaitReply(%r, %r, %r) -> reply handle %d',
                  self, handle, deadline, data, reply_to)

        queue = Queue.Queue()

        def _Receive(killed, data):
            LOG.debug('%r._Receive(%r, %r)', self, killed, data)
            queue.put((killed, data))

        self.AddHandleCB(_Receive, reply_to, persist=False)
        self._stream.Enqueue(handle, (False, (reply_to,) + data))

        try:
            killed, data = queue.get(True, deadline)
        except Queue.Empty:
            self._stream.Disconnect()
            raise TimeoutError('deadline exceeded.')

        if killed:
            raise StreamError('lost connection during call.')

        LOG.debug('%r._EnqueueAwaitReply(): got reply: %r', self, data)
        return data

    def CallWithDeadline(self, fn, deadline, *args, **kwargs):
        LOG.debug('%r.CallWithDeadline(%r, %r, *%r, **%r)',
                  self, fn, deadline, args, kwargs)

        if isinstance(fn, types.MethodType) and \
        isinstance(fn.im_self, (type, types.ClassType)):
            fn_class = fn.im_self.__name__
        else:
            fn_class = None

        call = (fn.__module__, fn_class, fn.__name__, args, kwargs)
        success, result = self.EnqueueAwaitReply(CALL_FUNCTION, deadline, call)

        if success:
            return result
        else:
            exc_obj, traceback = result
            exc_obj.real_traceback = traceback
            raise exc_obj

    def Call(self, fn, *args, **kwargs):
        return self.CallWithDeadline(fn, None, *args, **kwargs)

    def __repr__(self):
        bits = map(repr, filter(None, [self.name, self.hostname, self.username]))
        return 'Context(%s)' % ', '.join(bits)


class Waker(BasicStream):
    def __init__(self, broker):
        self._broker = broker
        rfd, wfd = os.pipe()
        self.read_side = Side(self, rfd)
        self.write_side = Side(self, wfd)
        broker.AddStream(self)

    def Wake(self):
        os.write(self.write_side.fd, ' ')

    def Receive(self):
        LOG.debug('%r: waking %r', self, self._broker)
        os.read(self.read_side.fd, 1)


class Listener(BasicStream):
    def __init__(self, broker, address=None, backlog=30):
        self._broker = broker
        self._sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._sock.bind(address or ('0.0.0.0', 0))
        self._sock.listen(backlog)
        self._listen_addr = self._sock.getsockname()
        self.read_side = Side(self, self._sock.fileno())
        broker.AddStream(self)

    def Receive(self):
        sock, addr = self._sock.accept()
        context = Context(self._broker, name=addr)
        Stream(context).Accept(sock.fileno(), sock.fileno())


class IoLogger(BasicStream):
    _buf = ''

    def __init__(self, broker, name):
        self._broker = broker
        self._name = name
        rfd, wfd = os.pipe()
        self.read_side = Side(self, rfd)
        self.write_side = Side(self, wfd)
        self._broker.AddStream(self)

    def _LogLines(self):
        while self._buf.find('\n') != -1:
            line, _, self._buf = self._buf.partition('\n')
            LOG.debug('%s: %s', self._name, line.rstrip('\n'))

    def Receive(self):
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

    def __init__(self):
        self._dead = False
        self._lock = threading.Lock()
        self._stopped = threading.Event()
        self._contexts = {}
        self._readers = set()
        self._writers = set()
        self._waker = None
        self._waker = Waker(self)

        self._thread = threading.Thread(target=self._Loop, name='Broker')
        self._thread.start()

    def CreateListener(self, address=None, backlog=30):
        """
        Listen on `address `for connections from newly spawned contexts.
        """
        self._listener = Listener(self, address, backlog)

    def _UpdateStream(self, stream):
        LOG.debug('_UpdateStream(%r)', stream)
        if stream.ReadMore() and stream.read_side.fileno():
            self._readers.add(stream.read_side)
        else:
            self._readers.discard(stream.read_side)

        if stream.WriteMore() and stream.write_side.fileno():
            self._writers.add(stream.write_side)
        else:
            self._writers.discard(stream.write_side)

    def UpdateStream(self, stream):
        LOG.debug('UpdateStream(%r)', stream)
        self._UpdateStream(stream)
        if self._waker:
            self._waker.Wake()

    def AddStream(self, stream):
        self.UpdateStream(stream)

    def Register(self, context):
        """
        Put a context under control of this broker.
        """
        LOG.debug('%r.Register(%r) -> r=%r w=%r', self, context,
                  context.GetStream().read_side,
                  context.GetStream().write_side)
        self.AddStream(context.GetStream())
        self._contexts[context.name] = context
        return context

    def GetLocal(self, name='default'):
        """
        Get the named context running on the local machine, creating it if it
        does not exist.
        """
        context = Context(self, name)
        context.SetStream(LocalStream(context)).Connect()
        return self.Register(context)

    def GetRemote(self, hostname, username, name=None, python_path=None):
        """
        Get the named remote context, creating it if it does not exist.
        """
        if name is None:
            name = 'econtext[%s@%s:%d]' %\
                (username, socket.gethostname(), os.getpid())

        context = Context(self, name, hostname, username)
        stream = SSHStream(context)
        if python_path:
            stream.python_path = python_path
        context.SetStream(stream)
        stream.Connect()
        return self.Register(context)

    def _LoopOnce(self):
        LOG.debug('%r.Loop()', self)
        #LOG.debug('readers = %r', self._readers)
        #LOG.debug('rfds = %r', [r.fileno() for r in self._readers])
        #LOG.debug('writers = %r', self._writers)
        #LOG.debug('wfds = %r', [w.fileno() for w in self._writers])
        rsides, wsides, _ = select.select(self._readers, self._writers, ())
        for side in rsides:
            LOG.debug('%r: POLLIN for %r', self, side.stream)
            side.stream.Receive()
            self._UpdateStream(side.stream)

        for side in wsides:
            LOG.debug('%r: POLLOUT for %r', self, side.stream)
            side.stream.Transmit()
            self._UpdateStream(side.stream)

    def _Loop(self):
        """
        Handle stream events until Finalize() is called.
        """
        try:
            while not self._dead:
                self._LoopOnce()

            for context in self._contexts.itervalues():
                stream = context.GetStream()
                if stream:
                    stream.Disconnect()

            self._stopped.set()
        except Exception:
            LOG.exception('Loop() crashed')

    def Wait(self):
        """
        Wait for the broker to stop.
        """
        self._stopped.wait()

    def Finalize(self):
        """
        Tell all active streams to disconnect.
        """
        self._dead = True
        self._waker.Wake()
        self.Wait()

    def __repr__(self):
        return 'econtext.Broker(<contexts=%s>)' % (self._contexts.keys(),)


def ExternalContextMain(context_name, parent_addr, key):
    syslog.openlog('%s:%s' % (getpass.getuser(), context_name), syslog.LOG_PID)
    syslog.syslog('initializing (parent=%s)' % (os.getenv('SSH_CLIENT'),))

    logging.basicConfig(level=logging.INFO)
    logging.getLogger('').handlers[0].formatter = Formatter(False)
    LOG.debug('ExternalContextMain(%r, %r, %r)', context_name, parent_addr, key)

    os.wait() # Reap the first stage.
    os.dup2(100, 0)
    os.close(100)

    broker = Broker()
    context = Context(broker, 'parent', parent_addr=parent_addr, key=key)

    stream = Stream(context)
    channel = Channel(stream, CALL_FUNCTION)

    #stdout_log = IoLogger(broker, 'stdout')
    #stderr_log = IoLogger(broker, 'stderr')

    stream.Accept(0, 1)
    os.close(0)
    os.dup2(2, 1)
    #os.dup2(stdout_log.write_side.fd, 1)
    #os.dup2(stderr_log.write_side.fd, 2)

    # stream = context.SetStream(Stream(context))
    # stream.
    # stream.Connect()
    broker.Register(context)

    importer = SlaveModuleImporter(context)
    sys.meta_path.append(importer)

    LOG.debug('start recv')
    for call_info in channel:
        LOG.debug('ExternalContextMain(): CALL_FUNCTION %r', call_info)
        reply_to, mod_name, class_name, func_name, args, kwargs = call_info

        try:
            fn = getattr(__import__(mod_name), func_name)
            stream.Enqueue(reply_to, (True, fn(*args, **kwargs)))
        except Exception, e:
            stream.Enqueue(reply_to, (False, (e, traceback.extract_stack())))

    broker.Finalize()
    LOG.error('ExternalContextMain exitting')
