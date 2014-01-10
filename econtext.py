#!/usr/bin/env python2.5

'''
Python External Execution Contexts.
'''

import atexit
import cPickle
import cStringIO
import commands
import getpass
import imp
import inspect
import os
import select
import signal
import struct
import subprocess
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

GET_MODULE = 0L
CALL_FUNCTION = 1L

DEBUG = True


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

def Log(fmt, *args):
  if DEBUG:
    sys.stderr.write('%d (%d): %s\n' % (os.getpid(), os.getppid(),
                                        (fmt%args).replace('econtext.', '')))


class PartialFunction(object):
  def __init__(self, fn, *partial_args):
    self.fn = fn
    self.partial_args = partial_args

  def __call__(self, *args, **kwargs):
    return self.fn(*(self.partial_args+args), **kwargs)

  def __repr__(self):
    return 'PartialFunction(%r, *%r)' % (self.fn, self.partial_args)


class Channel(object):
  def __init__(self, stream, handle):
    self._stream = stream
    self._handle = handle
    self._wake_event = threading.Event()
    self._queue_lock = threading.Lock()
    self._queue = []
    self._stream.AddHandleCB(self._InternalReceive, handle)

  def _InternalReceive(self, killed, data):
    '''
    Callback from the stream object; appends a tuple of
    (killed-or-closed, data) to the internal queue and wakes the internal
    event.

    Args:
      # Has the Stream object lost its connection?
      killed: bool
      # Has the remote Channel had Close() called? / the object passed to the
      # remote Send().
      data: (bool, object)
    '''
    Log('%r._InternalReceive(%r, %r)', self, killed, data)
    self._queue_lock.acquire()
    try:
      self._queue.append((killed or data[0], data[1]))
      self._wake_event.set()
    finally:
      self._queue_lock.release()

  def Close(self):
    '''
    Indicate this channel is closed to the remote side.
    '''
    Log('%r.Close()', self)
    self._stream.Enqueue(handle, (True, None))

  def Send(self, data):
    '''
    Send the given object to the remote side.
    '''
    Log('%r.Send(%r)', self, data)
    self._stream.Enqueue(handle, (False, data))

  def Receive(self, timeout=None):
    '''
    Receive the next object to arrive on this channel, or return if the
    optional timeout is reached.

    Args:
      timeout: float

    Returns:
      object
    '''
    Log('%r.Receive(%r)', self, timeout)
    if not self._queue:
      self._wake_event.wait(timeout)
      if not self._wake_event.isSet():
        return

    self._queue_lock.acquire()
    try:
      self._wake_event.clear()
      Log('%r.Receive() queue is %r', self, self._queue)
      closed, data = self._queue.pop(0)
      Log('%r.Receive() got closed=%r, data=%r', self, closed, data)
      if closed:
        raise ChannelError('Channel is closed.')
      return data
    finally:
      self._queue_lock.release()

  def __iter__(self):
    '''
    Return an iterator that yields objects arriving on this channel, until the
    channel is closed.
    '''
    while True:
      try:
        yield self.Receive()
      except ChannelError:
        return

  def __repr__(self):
    return 'econtext.Channel(%r, %r)' % (self._stream, self._handle)


class SlaveModuleImporter(object):
  '''
  This implements the import protocol described in PEP 302. It works like so:
  
  - Python asks it if it can import a module.
  - It asks Python (via imp module) if it can import the module.
  - If Python says yes, it says no.
  - If Python says no, it asks the parent context for the module.
  - If the module isn't returned by the parent, asplode, otherwise ask Python
    to load the returned module.

  This roundabout crap is necessary because the built-in importer is tried only
  after custom hooks are. A class method is provided for the parent context to
  satisfy the module request; it will only return modules that have been loaded
  in the parent context.
  '''

  def __init__(self, context):
    self._context = context

  def find_module(self, fullname, path=None):
    if not imp.find_module(fullname):
      return self

  def load_module(self, fullname):
    kind, data = self._context.EnqueueAwaitReply(GET_MODULE, fullname)

  def GetModule(cls, fullname):
    if fullname in sys.modules:
      pass

#
# Stream implementations.
#

class Stream(object):
  def __init__(self, context):
    self._context = context
    self._alive = True

    self._input_buf = self._output_buf = ''
    self._input_buf_lock = threading.Lock()
    self._output_buf_lock = threading.Lock()

    self._last_handle = 0
    self._handle_map = {}
    self._handle_lock = threading.Lock()

    self._func_refs = {}
    self._func_ref_lock = threading.Lock()

    self._pickler_file = cStringIO.StringIO()
    self._pickler = cPickle.Pickler(self._pickler_file)
    self._pickler.persistent_id = self._CheckFunctionPerID

    self._unpickler_file = cStringIO.StringIO()
    self._unpickler = cPickle.Unpickler(self._unpickler_file)
    self._unpickler.persistent_load = self._LoadFunctionFromPerID

  # Pickler/Unpickler support.

  def Pickle(self, obj):
    self._pickler.dump(obj)
    data = self._pickler_file.getvalue()
    self._pickler_file.seek(0)
    self._pickler_file.truncate(0)
    return data

  def Unpickle(self, data):
    Log('%r.Unpickle(%r)', self, data)
    self._unpickler_file.write(data)
    self._unpickler_file.seek(0)
    data = self._unpickler.load()
    self._unpickler_file.seek(0)
    self._unpickler_file.truncate(0)
    return data

  def _CheckFunctionPerID(self, obj):
    '''
    Please see the cPickle documentation. Given an object, return None
    indicating normal pickle processing or a string 'persistent ID'.

    Args:
      obj: object

    Returns:
      str
    '''
    if isinstance(obj, (types.FunctionType, types.MethodType)):
      pid = 'FUNC:' + repr(obj)
      self._func_refs[per_id] = obj
      return pid

  def _LoadFunctionFromPerID(self, pid):
    '''
    Please see the cPickle documentation. Given a string created by
    _CheckFunctionPerID, turn it into an object again.

    Args:
      pid: str

    Returns:
      object
    '''
    if not pid.startswith('FUNC:'):
      raise CorruptMessageError('unrecognized persistent ID received: %r', pid)
    return PartialFunction(self._CallPersistentWhatsit, pid)

  # I/O.

  def AllocHandle(self):
    '''
    Allocate a unique handle for this stream.

    Returns:
      long
    '''
    self._handle_lock.acquire()
    try:
      self._last_handle += 1L
    finally:
      self._handle_lock.release()
    return self._last_handle

  def AddHandleCB(self, fn, handle, persist=True):
    '''
    Arrange to invoke the given function for all messages tagged with the given
    handle. By default, process one message and discard this arrangement.

    Args:
      fn: callable
      handle: long
      persist: bool
    '''
    Log('%r.AddHandleCB(%r, %r, persist=%r)', self, fn, handle, persist)
    self._handle_lock.acquire()
    try:
      self._handle_map[handle] = persist, fn
    finally:
      self._handle_lock.release()

  def Receive(self):
    '''
    Handle the next complete message on the stream. Raise CorruptMessageError
    or IOError on failure.
    '''
    Log('%r.Receive()', self)
    chunk = os.read(self._rfd, 4096)
    if not chunk:
      raise StreamError('remote side hung up.')

    self._input_buf += chunk
    buffer_len = len(self._input_buf)
    if buffer_len < 4:
      return

    msg_len = struct.unpack('>L', self._input_buf[:4])[0]
    if buffer_len < msg_len-4:
      return

    try:
      handle, data = self.Unpickle(self._input_buf[4:msg_len+4])
      self._input_buf = self._input_buf[msg_len+4:]
      handle = long(handle)

      Log('%r.Receive(): decoded handle=%r; data=%r', self, handle, data)
      persist, fn = self._handle_map[handle]
      if not persist:
        del self._handle_map[handle]
    except KeyError, ex:
      raise CorruptMessageError('%r got invalid handle: %r', self, handle)
    except (TypeError, ValueError), ex:
      raise CorruptMessageError('%r got invalid message: %s', self, ex)

    fn(False, data)

  def Transmit(self):
    '''
    Transmit pending messages. Raises IOError on failure.
    '''
    Log('%r.Transmit()', self)
    written = os.write(self._wfd, self._output_buf[:4096])
    self._output_buf = self._output_buf[written:]
    if self._context and not self._output_buf:
      self._context.manager.UpdateStreamIOState(self)

  def Disconnect(self):
    '''
    Called to handle disconnects.
    '''
    Log('%r.Disconnect()', self)

    for fd in (self._rfd, self._wfd):
      os.close(fd)

    # Invoke each registered callback to indicate the connection has been
    # destroyed. This prevents pending Channels/RPCs from hanging forever.
    for handle, (persist, fn) in self._handle_map.iteritems():
      Log('%r.Disconnect(): killing stale callback handle=%r; fn=%r',
          self, handle, fn)
      fn(True, None)

    self._context.manager.UpdateStreamIOState(self)

  def GetIOState(self):
    '''
    Return a 3-tuple describing the instance's I/O state.

    Returns:
      (alive, input_fd, output_fd, has_output_buffered)
    '''
    return self._alive, self._rfd, self._wfd, bool(self._output_buf)

  def Enqueue(self, handle, data):
    Log('%r.Enqueue(%r, %r)', self, handle, data)

    self._output_buf_lock.acquire()
    try:
      encoded = self.Pickle((handle, data))
      self._output_buf += struct.pack('>L', len(encoded)) + encoded
    finally:
      self._output_buf_lock.release()
    self._context.manager.UpdateStreamIOState(self)

  # Misc.

  @classmethod
  def FromFDs(cls, context, rfd, wfd):
    Log('%r.FromFDs(%r, %r, %r)', cls, context, rfd, wfd)
    self = cls(context)
    self._rfd, self._wfd = rfd, wfd
    return self

  def __repr__(self):
    return 'econtext.%s(<context=%r>)' %\
           (self.__class__.__name__, self._context)


class LocalStream(Stream):
  '''
  Base for streams capable of starting new slaves.
  '''

  python_path = property(
    lambda self: getattr(self, '_python_path', sys.executable),
    lambda self, path: setattr(self, '_python_path', path),
    doc='The path to the remote Python interpreter.')

  def _GetModuleSource(self, killed, name):
    if not killed:
      return inspect.getsource(sys.modules[name])

  def __init__(self, context):
    super(LocalStream, self).__init__(context)
    self._permitted_modules = {}
    self._unpickler.find_global = self._FindGlobal
    self.AddHandleCB(self._GetModuleSource, handle=GET_MODULE)

  def _FindGlobal(self, module_name, class_name):
    '''
    See the cPickle documentation: given a module and class name, determine
    whether class referred to is safe for unpickling.

    Args:
      module_name: str
      class_name: str

    Returns:
      classobj or type
    '''
    if module_name not in self._permitted_modules:
      raise StreamError('context %r attempted to unpickle %r in module %r',
                        self._context, class_name, module_name)
    return getattr(sys.modules[module_name], class_name)

  def AllowModule(self, module_name):
    '''
    Add the given module to the list of permitted modules.

    Args:
      module_name: str
    '''
    self._permitted_modules.add(module_name)

  # Hexed and passed to 'python -c'. It forks, dups 0->100, creates a pipe,
  # then execs a new interpreter with a custom argv. CONTEXT_NAME is replaced
  # with the context name. Optimized for source size.
  def _FirstStage():
    import os,sys,zlib
    R,W=os.pipe()
    pid=os.fork()
    if pid:
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
    source = source.replace('  ', '\t')
    source = source.replace('CONTEXT_NAME', repr(self._context.name))
    return [ self.python_path, '-c',
             'exec "%s".decode("hex")' % (source.encode('hex'),) ]

  def __repr__(self):
    return '%s(%s)' % (self.__class__.__name__, self._context)

  # Public.

  @classmethod
  def Accept(cls, fd):
    raise NotImplemented

  def Connect(self):
    Log('%r.Connect()', self)
    self._child = subprocess.Popen(self.GetBootCommand(), stdin=subprocess.PIPE,
                                   stdout=subprocess.PIPE)
    self._wfd = self._child.stdin.fileno()
    self._rfd = self._child.stdout.fileno()
    Log('%r.Connect(): chlid process stdin=%r, stdout=%r',
        self, self._wfd, self._rfd)

    source = inspect.getsource(sys.modules[__name__])
    source += '\nExternalContextMain(%r)\n' % (self._context.name,)
    compressed = zlib.compress(source)

    preamble = str(len(compressed)) + '\n' + compressed
    self._child.stdin.write(preamble)
    self._child.stdin.flush()

    assert os.read(self._rfd, 3) == 'OK\n'

  def Disconnect(self):
    super(LocalStream, self).Disconnect()
    os.kill(self._child.pid, signal.SIGKILL)


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
    return bits + map(commands.mkarg, super(SSHStream, self).GetBootCommand())


class Context(object):
  '''
  Represents a remote context regardless of current connection method.
  '''

  def __init__(self, manager, name=None, hostname=None, username=None):
    self.manager = manager
    self.name = name
    self.hostname = hostname
    self.username = username
    self.tcp_port = None
    self._stream = None

  def GetStream(self):
    return self._stream

  def SetStream(self, stream):
    self._stream = stream
    return stream

  def EnqueueAwaitReply(self, handle, deadline, data):
    '''
    Send a message to the given handle and wait for a response with an optional
    timeout. The message contains (reply_handle, data), where reply_handle is
    the handle on which this function expects its reply.
    '''
    Log('%r.EnqueueAwaitReply(%r, %r, %r)', self, handle, deadline, data)
    reply_handle = self._stream.AllocHandle()
    reply_event = threading.Event()
    container = []

    def _Receive(killed, data):
      Log('%r._Receive(%r, %r)', self, killed, data)
      container.extend([killed, data])
      reply_event.set()

    self._stream.AddHandleCB(_Receive, reply_handle, persist=False)
    self._stream.Enqueue(CALL_FUNCTION, (False, (reply_handle,) + data))

    reply_event.wait(deadline)
    if not reply_event.isSet():
      self.Disconnect()
      raise TimeoutError('deadline exceeded.')

    killed, data = container
    if killed:
      raise StreamError('lost connection during call.')

    Log('%r._EnqueueAwaitReply(): got reply: %r', self, data)
    return data

  def CallWithDeadline(self, fn, deadline, *args, **kwargs):
    Log('%r.CallWithDeadline(%r, %r, *%r, **%r)', self, fn, deadline, args,
        kwargs)

    call = (fn.__module__, fn.__name__, args, kwargs)
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


class ContextManager(object):
  '''
  Context manager: this is responsible for keeping track of contexts, any
  stream that is associated with them, and for I/O multiplexing.
  '''

  def __init__(self):
    self._poller = select.poll()
    self._poller_fd_map = {}

    self._contexts_lock = threading.Lock()
    self._contexts = {}

    self._poller_changes_lock = threading.Lock()
    self._poller_changes = {}

    self._wake_rfd, self._wake_wfd = os.pipe()
    self._poller.register(self._wake_rfd)

    self._thread = threading.Thread(target=self.Loop, name='ContextManager')
    self._thread.setDaemon(True)
    self._thread.start()
    self._dead = False

  def Register(self, context):
    '''
    Put a context under control of this manager.
    '''
    self._contexts_lock.acquire()
    try:
      self._contexts[context.name] = context
      self.UpdateStreamIOState(context.GetStream())
    finally:
      self._contexts_lock.release()
    return context

  def GetLocal(self, name):
    '''
    Return the named local context, or create it if it doesn't exist.

    Args:
      name: 'my-local-context'
    Returns:
      econtext.Context
    '''
    context = Context(self, name)
    context.SetStream(LocalStream(context)).Connect()
    return self.Register(context)

  def GetRemote(self, hostname, username=None, name=None):
    '''
    Return the named remote context, or create it if it doesn't exist.
    '''
    if username is None:
      username = getpass.getuser()
    if name is None:
      name = 'econtext[%s@%s:%d]' %\
        (getpass.getuser(), os.getenv('HOSTNAME'), os.getpid())

    context = Context(self, name, hostname, username)
    context.SetStream(SSHStream(context)).Connect()
    return self.Register(context)

  def UpdateStreamIOState(self, stream):
    '''
    Update the manager's internal state regarding the specified stream by
    marking its FDs for polling as appropriate.

    Args:
      stream: econtext.Stream
    '''
    Log('%r.UpdateStreamIOState(%r)', self, stream)

    self._poller_changes_lock.acquire()
    try:
      self._poller_changes[stream] = None
    finally:
      self._poller_changes_lock.release()
    os.write(self._wake_wfd, ' ')

  def _DoChangedStreams(self):
    '''
    Walk the list of streams indicated as having an updated I/O state by
    UpdateStreamIOState. Poller registration updates must be done in serial
    with calls to its poll() method.
    '''
    Log('%r._DoChangedStreams()', self)

    self._poller_changes_lock.acquire()
    try:
      changes = self._poller_changes.keys()
      self._poller_changes = {}
    finally:
      self._poller_changes_lock.release()

    for stream in changes:
      alive, ifd, ofd, has_output = stream.GetIOState()

      if not alive:
        for fd in (ifd, ofd):
          del self._poller_fd_map[fd]
        del self._contexts[stream._context]
        return

      if has_output:
        self._poller.register(ofd, select.POLLOUT)
        self._poller_fd_map[ofd] = stream
      elif ofd in self._poller_fd_map:
        self._poller.unregister(ofd)
        del self._poller_fd_map[ofd]

      self._poller.register(ifd, select.POLLIN)
      self._poller_fd_map[ifd] = stream

  def Loop(self):
    '''
    Handle stream events until Finalize() is called.
    '''
    while not self._dead:
      Log('%r.Loop(): %r', self, self._poller_fd_map)
      for fd, event in self._poller.poll():
        if fd == self._wake_rfd:
          Log('%r: got event on wake_rfd=%d.', self, self._wake_rfd)
          os.read(self._wake_rfd, 1)
          self._DoChangedStreams()
        elif event & select.POLLHUP:
          Log('%r: POLLHUP on %d; calling %r', self, fd,
              self._poller_fd_map[fd].Disconnect)
          self._poller_fd_map[fd].Disconnect()
        elif event & select.POLLIN:
          Log('%r: POLLIN on %d; calling %r', self, fd,
              self._poller_fd_map[fd].Receive)
          self._poller_fd_map[fd].Receive()
        elif event & select.POLLOUT:
          Log('%r: POLLOUT on %d', self, fd)
          Log('%r: POLLOUT on %d; calling %r', self, fd,
              self._poller_fd_map[fd].Transmit)
          self._poller_fd_map[fd].Transmit()
        elif event & select.POLLNVAL:
          Log('%r: POLLNVAL for %d, unregistering it.', self, fd)
          self._poller.unregister(fd)

  def Finalize(self):
    '''
    Tell all active streams to disconnect.
    '''
    self._dead = True
    self._contexts_lock.acquire()
    try:
      for name, context in self._contexts.iteritems():
        stream = context.GetStream()
        if stream:
          stream.Disconnect()
    finally:
      self._contexts_lock.release()

  def __repr__(self):
    return 'econtext.ContextManager(<contexts=%s>)' % (self._contexts.keys(),)


def ExternalContextMain(context_name):
  Log('ExternalContextMain(%r)', context_name)
  assert os.wait()[1] == 0, 'first stage did not exit cleanly.'

  syslog.openlog('%s:%s' % (getpass.getuser(), context_name), syslog.LOG_PID)
  syslog.syslog('initializing (parent=%s)' % (os.getenv('SSH_CLIENT'),))

  os.dup2(100, 0)
  os.close(100)

  manager = ContextManager()
  context = Context(manager, 'parent')

  stream = context.SetStream(Stream.FromFDs(context, rfd=0, wfd=1))
  manager.Register(context)

  for call_info in Channel(stream, CALL_FUNCTION):
    Log('ExternalContextMain(): CALL_FUNCTION %r', call_info)
    reply_handle, mod_name, func_name, args, kwargs = call_info
    fn = getattr(__import__(mod_name), func_name)

    try:
      stream.Enqueue(reply_handle, (True, fn(*args, **kwargs)))
    except Exception, e:
      stram.Enqueue(reply_handle, (False, (e, traceback.extract_stack())))
