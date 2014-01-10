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
import sched
import select
import signal
import socket
import struct
import subprocess
import sys
import syslog
import textwrap
import threading
import time
import traceback
import types
import zlib


#
# Module-level data.
#

GET_MODULE_SOURCE = 0L
CALL_FUNCTION = 1L

_manager = None
_manager_thread = None

DEBUG = True


#
# Exceptions.
#

class ContextError(Exception):
  'Raised when a problem occurs with a context.'
  def __init__(self, fmt, *args):
    Exception.__init__(self, fmt % args)

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


class FunctionProxy(object):
  __slots__ = ['_context', '_per_id']

  def __init__(self, context, per_id):
    self._context = context
    self._per_id = per_id

  def __call__(self, *args, **kwargs):
    self._context._Call(self._per_id, args, kwargs)


class SlaveModuleImporter(object):
  '''
  This objects implements the import hook protocol defined in
  http://www.python.org/dev/peps/pep-0302/; the interpreter will ask it if it
  knows how to load each module, it will in turn ask the interpreter if it
  knows how to do the load, and if so, it will say it can't. This round about
  crap is necessary because the module import mechanism is brutal.

  When the built in importer can't load a module, we try requesting it from the
  parent context.
  '''

  def __init__(self, context):
    self._context = context

  def find_module(self, fullname, path=None):
    if imp.find_module(fullname):
      return
    return self

  def load_module(self, fullname):
    kind, data = self._context.


#
# Stream implementations.
#

class Stream(object):
  def __init__(self, context, secure_unpickler=True):
    self._context = context
    self._sched_id = 0.0
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

    if secure_unpickler:
      self._permitted_modules = {}
      self._unpickler.find_global = self._FindGlobal

  # Pickler/Unpickler support.

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
    return FunctionProxy(self, pid)

  def _FindGlobal(self, module_name, class_name):
    '''
    Please see the cPickle documentation. Given a module and class name,
    determine whether class referred to is safe for unpickling.

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

  # I/O.

  def AllocHandle(self):
    '''
    Allocate a unique communications handle for this stream.

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

    Log('%r.Receive() -> msg_len=%d; msg=%r', self, msg_len,
        self._input_buf[4:msg_len+4])

    try:
      # TODO: wire in the per-instance unpickler.
      handle, data = cPickle.loads(self._input_buf[4:msg_len+4])
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

    fn(handle, False, data)

  def Transmit(self):
    '''
    Transmit pending messages. Raises IOError on failure.
    '''

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
      try:
        os.close(fd)
        Log('%r.Disconnect(): closed fd %d', self, fd)
      except OSError:
        pass

    # Invoke each registered non-persistent handle callback to indicate the
    # connection has been destroyed. This prevents pending RPCs from hanging
    # infinitely.
    for handle, (persist, fn) in self._handle_map.iteritems():
      if not persist:
        Log('%r.Disconnect(): killing stale callback handle=%r; fn=%r',
            self, handle, fn)
        fn(handle, True, None)

    self._context.manager.UpdateStreamIOState(self)

  def GetIOState(self):
    '''
    Return a 3-tuple describing the instance's I/O state.

    Returns:
      (alive, input_fd, output_fd, has_output_buffered)
    '''

    # TODO: this alive flag is stupid.
    return self._alive, self._rfd, self._wfd, bool(self._output_buf)

  def Enqueue(self, handle, data):
    Log('%r.Enqueue(%r, %r)', self, handle, data)

    self._output_buf_lock.acquire()
    try:
      # TODO: wire in the per-instance pickler.
      encoded = cPickle.dumps((handle, data))
      self._output_buf += struct.pack('>L', len(encoded)) + encoded
    finally:
      self._output_buf_lock.release()
    self._context.manager.UpdateStreamIOState(self)

  # Misc.

  def FromFDs(cls, context, rfd, wfd):
    Log('%r.FromFDs(%r, %r, %r)', cls, context, rfd, wfd)
    self = cls(context)
    self._rfd, self._wfd = rfd, wfd
    return self
  FromFDs = classmethod(FromFDs)

  def __repr__(self):
    return 'econtext.%s(<context=%r>)' %\
           (self.__class__.__name__, self._context)


class SlaveStream(Stream):
  def __init__(self, context, secure_unpickler=True):
    super(SlaveStream, self).__init__(context, secure_unpickler)
    self.AddHandleCB(self._CallFunction, handle=CALL_FUNCTION)

  def _CallFunction(self, handle, killed, data):
    Log('%r._CallFunction(%r, %r)', self, handle, data)

    try:
      reply_handle, mod_name, func_name, args, kwargs = data
      try:
        module = __import__(mod_name)
      except ImportError:
        raise # TODO: module source callback.
      # (success, data)
      self.Enqueue(reply_handle,
                   (True, getattr(module, func_name)(*args, **kwargs)))
    except Exception, e:
      self.Enqueue(reply_handle, (False, (e, traceback.extract_stack())))


class LocalStream(Stream):
  """
  Base for streams capable of starting new slaves.
  """

  python_path = property(
    lambda self: getattr(self, '_python_path', sys.executable),
    lambda self, path: setattr(self, '_python_path', path),
    doc='The path to the remote Python interpreter.')

  def _GetModuleSource(self, name):
    return inspect.getsource(sys.modules[name])

  def __init__(self, context, secure_unpickler=True):
    super(LocalStream, self).__init__(context, secure_unpickler)
    self.AddHandleCB(self._GetModuleSource, handle=GET_MODULE_SOURCE)

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
    source += '\nExternalContextImpl.Main(%r)\n' % (self._context.name,)
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
  """
  Represents a remote context regardless of current connection method.
  """

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

  def CallWithDeadline(self, fn, deadline, *args, **kwargs):
    Log('%r.CallWithDeadline(%r, %r, *%r, **%r)', self, fn, deadline, args,
        kwargs)
    handle = self._stream.AllocHandle()
    reply_event = threading.Event()
    container = []

    def _Receive(handle, killed, data):
      Log('%r._Receive(%r, %r, %r)', self, handle, killed, data)
      container.extend([killed, data])
      reply_event.set()

    self._stream.AddHandleCB(_Receive, handle, persist=False)
    call = (handle, fn.__module__, fn.__name__, args, kwargs)
    self._stream.Enqueue(CALL_FUNCTION, call)

    reply_event.wait(deadline)
    if not reply_event.isSet():
      self.Disconnect()
      raise TimeoutError('deadline exceeded.')

    Log('%r._Receive(): got reply, container is %r', self, container)
    killed, data = container

    if killed:
      raise StreamError('lost connection during call.')

    success, result = data
    if success:
      return result
    else:
      exc_obj, traceback = result
      exc_obj.real_traceback = traceback
      raise exc_obj

  def Call(self, fn, *args, **kwargs):
    return self.CallWithDeadline(fn, None, *args, **kwargs)

  def Kill(self, deadline=30):
    self.CallWithDeadline(os.kill, deadline,
                          -self.Call(os.getpgrp), signal.SIGTERM)

  def __repr__(self):
    bits = map(repr, filter(None, [self.name, self.hostname, self.username]))
    return 'Context(%s)' % ', '.join(bits)


class ContextManager(object):
  '''
  Context manager: this is responsible for keeping track of contexts, any
  stream that is associated with them, and for I/O multiplexing.
  '''

  def __init__(self):
    self._scheduler = sched.scheduler(time.time, self.OneShot)
    self._idle_timeout = 0
    self._dead = False
    self._kill_on_empty = False

    self._poller = select.poll()
    self._poller_fd_map = {}

    self._contexts_lock = threading.Lock()
    self._contexts = {}

    self._poller_changes_lock = threading.Lock()
    self._poller_changes = {}

    self._wake_rfd, self._wake_wfd = os.pipe()
    self._poller.register(self._wake_rfd)

  def SetKillOnEmpty(self, kill_on_empty=True):
    '''
    Indicate the main loop should exit when there are no remaining sessions
    open.
    '''

    self._kill_on_empty = kill_on_empty

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

  def GetRemote(self, hostname, name=None, username=None):
    '''
    Return the named remote context, or create it if it doesn't exist.
    '''

    if username is None:
      username = getpass.getuser()
    if name is None:
      name = 'econtext[%s@%s:%d]' %\
        (getpass.getuser(), socket.gethostname(), os.getpid())

    context = Context(self, name, hostname, username)
    context.SetStream(SSHStream(context)).Connect()
    return self.Register(context)

  def UpdateStreamIOState(self, stream):
    '''
    Update the manager's internal state regarding the specified stream. This
    marks its FDs for polling as appropriate, and resets its idle counter.

    Args:
      stream: econtext.Stream
    '''

    Log('%r.UpdateStreamIOState(%r)', self, stream)

    self._poller_changes_lock.acquire()
    try:
      self._poller_changes[stream] = None
      if self._idle_timeout:
        if stream._sched_id:
          self._scheduler.cancel(stream._sched_id)
        self._scheduler.enter(self._idle_timeout, 0, stream.Disconnect, ())
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

      if not alive: # no fd = closed stream.
        Log('here2')
        for fd in (ifd, ofd):
          try:
            self._poller.unregister(fd)
            Log('unregistered fd=%d from poller', fd)
          except KeyError:
            Log('failed to unregister fd=%d from poller', fd)
          try:
            del self._poller_fd_map[fd]
            Log('unregistered fd=%d from poller map', fd)
          except KeyError:
            Log('failed to unregister fd=%d from poller map', fd)
        del self._contexts[stream._context]

      if has_output:
        self._poller.register(ofd, select.POLLOUT)
        self._poller_fd_map[ofd] = stream
      elif ofd in self._poller_fd_map:
        self._poller.unregister(ofd)
        del self._poller_fd_map[ofd]

      self._poller.register(ifd, select.POLLIN)
      self._poller_fd_map[ifd] = stream

  def OneShot(self, timeout=None):
    '''
    Poll once for I/O and return after all processing is complete, optionally
    terminating after some number of seconds.

    Args:
      timeout: int or float
    '''

    if timeout == 0: # scheduler behaviour we don't require.
      return

    Log('%r.OneShot(): _poller_fd_map=%r', self, self._poller_fd_map)

    for fd, event in self._poller.poll(timeout):
      if fd == self._wake_rfd:
        Log('%r: got event on wake_rfd=%d.', self, self._wake_rfd)
        os.read(self._wake_rfd, 1)
        self._DoChangedStreams()
        break
      elif event & select.POLLHUP:
        Log('%r: POLLHUP on %d; calling %r', self, fd,
            self._poller_fd_map[fd].Disconnect)
        self._poller_fd_map[fd].Disconnect()
      elif event & select.POLLIN:
        Log('%r: POLLIN on %d; calling %r', self, fd,
            self._poller_fd_map[fd].Receive)
        self._poller_fd_map[fd].Receive()
      elif event & select.POLLOUT:
        Log('%r: POLLOUT on %d; calling %r', self, fd,
            self._poller_fd_map[fd].Transmit)
        self._poller_fd_map[fd].Transmit()
      elif event & select.POLLNVAL:
        # GAY
        self._poller.unregister(fd)

  def Loop(self):
    '''
    Handle stream events until Finalize() is called.
    '''

    while (not self._dead) or (self._kill_on_empty and not self._contexts):
      # TODO: why the fuck is self._scheduler.empty() returning True?!
      if not len(self._scheduler.queue):
        self.OneShot()
      else:
        Log('self._scheduler.empty() -> %r', self._scheduler.empty())
        Log('not not self._scheduler.queue -> %r',
            not not self._scheduler.queue)
        Log('%r._scheduler.run() -> %r', self, self._scheduler.queue)
        raise SystemExit
        self._scheduler.run()

  def SetIdleTimeout(self, timeout):
    '''
    Set the number of seconds after which an idle stream connected to a remote
    context is eligible for disconnection.

    Args:
      timeout: int or float
    '''
    self._idle_timeout = timeout

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


class ExternalContextImpl(object):
  def Main(cls, context_name):
    assert os.wait()[1] == 0, 'first stage did not exit cleanly.'

    syslog.openlog('%s:%s' % (getpass.getuser(), context_name), syslog.LOG_PID)

    parent_host = os.getenv('SSH_CLIENT')
    syslog.syslog('initializing (parent_host=%s)' % (parent_host,))

    os.dup2(100, 0)
    os.close(100)

    manager = ContextManager()
    manager.SetKillOnEmpty()
    context = Context(manager, 'parent')

    stream = context.SetStream(SlaveStream.FromFDs(context, rfd=0, wfd=1))
    manager.Register(context)

    try:
      manager.Loop()
    except StreamError, e:
      syslog.syslog('exit: ' + str(e))
      os.kill(-os.getpgrp(), signal.SIGKILL)
  Main = classmethod(Main)

  def __repr__(self):
    return 'ExternalContextImpl(%r)' % (self.name,)


#
# Simple interface.
#

def Init(idle_secs=60*60):
  '''
  Initialize the simple interface.

  Args:
    # Seconds to keep an unused context alive or None for infinite.
    idle_secs: 3600 or None
  '''

  global _manager
  global _manager_thread

  if _manager:
    return _manager

  _manager = ContextManager()
  _manager.SetIdleTimeout(idle_secs)
  _manager_thread = threading.Thread(target=_manager.Loop)
  _manager_thread.setDaemon(True)
  _manager_thread.start()
  atexit.register(Finalize)
  return _manager


def Finalize():
  global _manager
  global _manager_thread

  if _manager is not None:
    _manager.Finalize()
    _manager = None


def CallWithDeadline(hostname, username, fn, deadline, *args, **kwargs):
  '''
  Make a function call in the context of a remote host. Set a maximum deadline
  in seconds after which it is assumed the call failed.

  Args:
    # Hostname or address of remote host.
    hostname: str
    # Username to connect as, or None for current user.
    username: str or None
    # Seconds until we assume the call has failed.
    deadline: float or None
    # The function to execute in the remote context.
    fn: staticmethod or classmethod or types.FunctionType

  Returns:
    # Function's return value.
    object
  '''

  context = Init().GetRemote(hostname, username=username)
  return context.CallWithDeadline(fn, deadline, *args, **kwargs)


def Call(hostname, username, fn, *args, **kwargs):
  '''
  Like CallWithDeadline, but with no deadline.
  '''

  return CallWithDeadline(hostname, username, fn, None, *args, **kwargs)
