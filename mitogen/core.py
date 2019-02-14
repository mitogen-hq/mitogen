# Copyright 2019, David Wilson
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

# !mitogen: minify_safe

"""
This module implements most package functionality, but remains separate from
non-essential code in order to reduce its size, since it is also serves as the
bootstrap implementation sent to every new slave context.
"""

import binascii
import collections
import encodings.latin_1
import errno
import fcntl
import itertools
import linecache
import logging
import os
import pickle as py_pickle
import pstats
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

# Python >3.7 deprecated the imp module.
warnings.filterwarnings('ignore', message='the imp module is deprecated')
import imp

# Absolute imports for <2.5.
select = __import__('select')

try:
    import cProfile
except ImportError:
    cProfile = None

try:
    import thread
except ImportError:
    import threading as thread

try:
    import cPickle as pickle
except ImportError:
    import pickle

try:
    from cStringIO import StringIO as BytesIO
except ImportError:
    from io import BytesIO

try:
    BaseException
except NameError:
    BaseException = Exception

try:
    ModuleNotFoundError
except NameError:
    ModuleNotFoundError = ImportError

# TODO: usage of 'import' after setting __name__, but before fixing up
# sys.modules generates a warning. This happens when profiling = True.
warnings.filterwarnings('ignore',
    "Parent module 'mitogen' not found while handling absolute import")

LOG = logging.getLogger('mitogen')
IOLOG = logging.getLogger('mitogen.io')
IOLOG.setLevel(logging.INFO)

LATIN1_CODEC = encodings.latin_1.Codec()

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
CALL_SERVICE = 110

#: Special value used to signal disconnection or the inability to route a
#: message, when it appears in the `reply_to` field. Usually causes
#: :class:`mitogen.core.ChannelError` to be raised when it is received.
#:
#: It indicates the sender did not know how to process the message, or wishes
#: no further messages to be delivered to it. It is used when:
#:
#:  * a remote receiver is disconnected or explicitly closed.
#:  * a related message could not be delivered due to no route existing for it.
#:  * a router is being torn down, as a sentinel value to notify
#:    :meth:`mitogen.core.Router.add_handler` callbacks to clean up.
IS_DEAD = 999

try:
    BaseException
except NameError:
    BaseException = Exception

IS_WSL = 'Microsoft' in os.uname()[2]
PY24 = sys.version_info < (2, 5)
PY3 = sys.version_info > (3,)
if PY3:
    b = str.encode
    BytesType = bytes
    UnicodeType = str
    FsPathTypes = (str,)
    BufferType = lambda buf, start: memoryview(buf)[start:]
    long = int
else:
    b = str
    BytesType = str
    FsPathTypes = (str, unicode)
    BufferType = buffer
    UnicodeType = unicode

AnyTextType = (BytesType, UnicodeType)

try:
    next
except NameError:
    next = lambda it: it.next()


#: Default size for calls to :meth:`Side.read` or :meth:`Side.write`, and the
#: size of buffers configured by :func:`mitogen.parent.create_socketpair`. This
#: value has many performance implications, 128KiB seems to be a sweet spot.
#:
#: * When set low, large messages cause many :class:`Broker` IO loop
#:   iterations, burning CPU and reducing throughput.
#: * When set high, excessive RAM is reserved by the OS for socket buffers (2x
#:   per child), and an identically sized temporary userspace buffer is
#:   allocated on each read that requires zeroing, and over a particular size
#:   may require two system calls to allocate/deallocate.
#:
#: Care must be taken to ensure the underlying kernel object and receiving
#: program support the desired size. For example,
#:
#: * Most UNIXes have TTYs with fixed 2KiB-4KiB buffers, making them unsuitable
#:   for efficient IO.
#: * Different UNIXes have varying presets for pipes, which may not be
#:   configurable. On recent Linux the default pipe buffer size is 64KiB, but
#:   under memory pressure may be as low as 4KiB for unprivileged processes.
#: * When communication is via an intermediary process, its internal buffers
#:   effect the speed OS buffers will drain. For example OpenSSH uses 64KiB
#:   reads.
#:
#: An ideal :class:`Message` has a size that is a multiple of
#: :data:`CHUNK_SIZE` inclusive of headers, to avoid wasting IO loop iterations
#: writing small trailer chunks.
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
    """Base for all exceptions raised by Mitogen.

    :param str fmt:
        Exception text, or format string if `args` is non-empty.
    :param tuple args:
        Format string arguments.
    """
    def __init__(self, fmt=None, *args):
        if args:
            fmt %= args
        if fmt and not isinstance(fmt, UnicodeType):
            fmt = fmt.decode('utf-8')
        Exception.__init__(self, fmt)


class LatchError(Error):
    """Raised when an attempt is made to use a :class:`mitogen.core.Latch`
    that has been marked closed."""
    pass


class Blob(BytesType):
    """A serializable bytes subclass whose content is summarized in repr()
    output, making it suitable for logging binary data."""
    def __repr__(self):
        return '[blob: %d bytes]' % len(self)

    def __reduce__(self):
        return (Blob, (BytesType(self),))


class Secret(UnicodeType):
    """A serializable unicode subclass whose content is masked in repr()
    output, making it suitable for logging passwords."""
    def __repr__(self):
        return '[secret]'

    if not PY3:
        # TODO: what is this needed for in 2.x?
        def __str__(self):
            return UnicodeType(self)

    def __reduce__(self):
        return (Secret, (UnicodeType(self),))


class Kwargs(dict):
    """
    A serializable dict subclass that indicates its keys should be coerced to
    Unicode on Python 3 and bytes on Python<2.6.

    Python 2 produces keyword argument dicts whose keys are bytes, requiring a
    helper to ensure compatibility with Python 3 where Unicode is required,
    whereas Python 3 produces keyword argument dicts whose keys are Unicode,
    requiring a helper for Python 2.4/2.5, where bytes are required.
    """
    if PY3:
        def __init__(self, dct):
            for k, v in dct.items():
                if type(k) is bytes:
                    self[k.decode()] = v
                else:
                    self[k] = v
    elif sys.version_info < (2, 6):
        def __init__(self, dct):
            for k, v in dct.iteritems():
                if type(k) is unicode:
                    self[k.encode()] = v
                else:
                    self[k] = v

    def __repr__(self):
        return 'Kwargs(%s)' % (dict.__repr__(self),)

    def __reduce__(self):
        return (Kwargs, (dict(self),))


class CallError(Error):
    """
    Serializable :class:`Error` subclass raised when :meth:`Context.call()
    <mitogen.parent.Context.call>` fails. A copy of the traceback from the
    external context is appended to the exception message.
    """
    def __init__(self, fmt=None, *args):
        if not isinstance(fmt, BaseException):
            Error.__init__(self, fmt, *args)
        else:
            e = fmt
            cls = e.__class__
            fmt = '%s.%s: %s' % (cls.__module__, cls.__name__, e)
            tb = sys.exc_info()[2]
            if tb:
                fmt += '\n'
                fmt += ''.join(traceback.format_tb(tb))
            Error.__init__(self, fmt)

    def __reduce__(self):
        return (_unpickle_call_error, (self.args[0],))


def _unpickle_call_error(s):
    if not (type(s) is UnicodeType and len(s) < 10000):
        raise TypeError('cannot unpickle CallError: bad input')
    return CallError(s)


class ChannelError(Error):
    """Raised when a channel dies or has been closed."""
    remote_msg = 'Channel closed by remote end.'
    local_msg = 'Channel closed by local end.'


class StreamError(Error):
    """Raised when a stream cannot be established."""
    pass


class TimeoutError(Error):
    """Raised when a timeout occurs on a stream."""
    pass


def to_text(o):
    """Coerce `o` to Unicode by decoding it from UTF-8 if it is an instance of
    :class:`bytes`, otherwise pass it to the :class:`str` constructor. The
    returned object is always a plain :class:`str`, any subclass is removed."""
    if isinstance(o, BytesType):
        return o.decode('utf-8')
    return UnicodeType(o)


# Python 2.4
try:
    any
except NameError:
    def any(it):
        for elem in it:
            if elem:
                return True


def _partition(s, sep, find):
    """
    (str|unicode).(partition|rpartition) for Python 2.4/2.5.
    """
    idx = find(sep)
    if idx != -1:
        left = s[0:idx]
        return left, sep, s[len(left)+len(sep):]


if hasattr(UnicodeType, 'rpartition'):
    str_partition = UnicodeType.partition
    str_rpartition = UnicodeType.rpartition
    bytes_partition = BytesType.partition
else:
    def str_partition(s, sep):
        return _partition(s, sep, s.find) or (s, u'', u'')
    def str_rpartition(s, sep):
        return _partition(s, sep, s.rfind) or (u'', u'', s)
    def bytes_partition(s, sep):
        return _partition(s, sep, s.find) or (s, '', '')


def has_parent_authority(msg, _stream=None):
    """Policy function for use with :class:`Receiver` and
    :meth:`Router.add_handler` that requires incoming messages to originate
    from a parent context, or on a :class:`Stream` whose :attr:`auth_id
    <Stream.auth_id>` has been set to that of a parent context or the current
    context."""
    return (msg.auth_id == mitogen.context_id or
            msg.auth_id in mitogen.parent_ids)


def listen(obj, name, func):
    """
    Arrange for `func(*args, **kwargs)` to be invoked when the named signal is
    fired by `obj`.
    """
    signals = vars(obj).setdefault('_signals', {})
    signals.setdefault(name, []).append(func)


def fire(obj, name, *args, **kwargs):
    """
    Arrange for `func(*args, **kwargs)` to be invoked for every function
    registered for the named signal on `obj`.
    """
    signals = vars(obj).get('_signals', {})
    for func in signals.get(name, ()):
        func(*args, **kwargs)


def takes_econtext(func):
    func.mitogen_takes_econtext = True
    return func


def takes_router(func):
    func.mitogen_takes_router = True
    return func


def is_blacklisted_import(importer, fullname):
    """
    Return :data:`True` if `fullname` is part of a blacklisted package, or if
    any packages have been whitelisted and `fullname` is not part of one.

    NB:
      - If a package is on both lists, then it is treated as blacklisted.
      - If any package is whitelisted, then all non-whitelisted packages are
        treated as blacklisted.
    """
    return ((not any(fullname.startswith(s) for s in importer.whitelist)) or
                (any(fullname.startswith(s) for s in importer.blacklist)))


def set_cloexec(fd):
    """Set the file descriptor `fd` to automatically close on
    :func:`os.execve`. This has no effect on file descriptors inherited across
    :func:`os.fork`, they must be explicitly closed through some other means,
    such as :func:`mitogen.fork.on_fork`."""
    flags = fcntl.fcntl(fd, fcntl.F_GETFD)
    assert fd > 2
    fcntl.fcntl(fd, fcntl.F_SETFD, flags | fcntl.FD_CLOEXEC)


def set_nonblock(fd):
    """Set the file descriptor `fd` to non-blocking mode. For most underlying
    file types, this causes :func:`os.read` or :func:`os.write` to raise
    :class:`OSError` with :data:`errno.EAGAIN` rather than block the thread
    when the underlying kernel buffer is exhausted."""
    flags = fcntl.fcntl(fd, fcntl.F_GETFL)
    fcntl.fcntl(fd, fcntl.F_SETFL, flags | os.O_NONBLOCK)


def set_block(fd):
    """Inverse of :func:`set_nonblock`, i.e. cause `fd` to block the thread
    when the underlying kernel buffer is exhausted."""
    flags = fcntl.fcntl(fd, fcntl.F_GETFL)
    fcntl.fcntl(fd, fcntl.F_SETFL, flags & ~os.O_NONBLOCK)


def io_op(func, *args):
    """Wrap `func(*args)` that may raise :class:`select.error`,
    :class:`IOError`, or :class:`OSError`, trapping UNIX error codes relating
    to disconnection and retry events in various subsystems:

    * When a signal is delivered to the process on Python 2, system call retry
      is signalled through :data:`errno.EINTR`. The invocation is automatically
      restarted.
    * When performing IO against a TTY, disconnection of the remote end is
      signalled by :data:`errno.EIO`.
    * When performing IO against a socket, disconnection of the remote end is
      signalled by :data:`errno.ECONNRESET`.
    * When performing IO against a pipe, disconnection of the remote end is
      signalled by :data:`errno.EPIPE`.

    :returns:
        Tuple of `(return_value, disconnect_reason)`, where `return_value` is
        the return value of `func(*args)`, and `disconnected` is an exception
        instance when disconnection was detected, otherwise :data:`None`.
    """
    while True:
        try:
            return func(*args), None
        except (select.error, OSError, IOError):
            e = sys.exc_info()[1]
            _vv and IOLOG.debug('io_op(%r) -> OSError: %s', func, e)
            if e.args[0] == errno.EINTR:
                continue
            if e.args[0] in (errno.EIO, errno.ECONNRESET, errno.EPIPE):
                return None, e
            raise


class PidfulStreamHandler(logging.StreamHandler):
    """A :class:`logging.StreamHandler` subclass used when
    :meth:`Router.enable_debug() <mitogen.master.Router.enable_debug>` has been
    called, or the `debug` parameter was specified during context construction.
    Verifies the process ID has not changed on each call to :meth:`emit`,
    reopening the associated log file when a change is detected.

    This ensures logging to the per-process output files happens correctly even
    when uncooperative third party components call :func:`os.fork`.
    """
    #: PID that last opened the log file.
    open_pid = None

    #: Output path template.
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
        logging.StreamHandler.emit(self, record)


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
_profile_fmt = os.environ.get(
    'MITOGEN_PROFILE_FMT',
    '/tmp/mitogen.stats.%(pid)s.%(identity)s.%(now)s.%(ext)s',
)


def _profile_hook(name, func, *args):
    """
    Call `func(*args)` and return its result. This function is replaced by
    :func:`_real_profile_hook` when :func:`enable_profiling` is called. This
    interface is obsolete and will be replaced by a signals-based integration
    later on.
    """
    return func(*args)


def _real_profile_hook(name, func, *args):
    profiler = cProfile.Profile()
    profiler.enable()
    try:
        return func(*args)
    finally:
        path = _profile_fmt % {
            'now': int(1e6 * time.time()),
            'identity': name,
            'pid': os.getpid(),
            'ext': '%s'
        }
        profiler.dump_stats(path % ('pstats',))
        profiler.create_stats()
        fp = open(path % ('log',), 'w')
        try:
            stats = pstats.Stats(profiler, stream=fp)
            stats.sort_stats('cumulative')
            stats.print_stats()
        finally:
            fp.close()


def enable_profiling(econtext=None):
    global _profile_hook
    _profile_hook = _real_profile_hook


def import_module(modname):
    """
    Import `module` and return the attribute named `attr`.
    """
    return __import__(modname, None, None, [''])


class Py24Pickler(py_pickle.Pickler):
    """
    Exceptions were classic classes until Python 2.5. Sadly for 2.4, cPickle
    offers little control over how a classic instance is pickled. Therefore 2.4
    uses a pure-Python pickler, so CallError can be made to look as it does on
    newer Pythons.

    This mess will go away once proper serialization exists.
    """
    @classmethod
    def dumps(cls, obj, protocol):
        bio = BytesIO()
        self = cls(bio, protocol=protocol)
        self.dump(obj)
        return bio.getvalue()

    def save_exc_inst(self, obj):
        if isinstance(obj, CallError):
            func, args = obj.__reduce__()
            self.save(func)
            self.save(args)
            self.write(py_pickle.REDUCE)
        else:
            py_pickle.Pickler.save_inst(self, obj)

    if PY24:
        dispatch = py_pickle.Pickler.dispatch.copy()
        dispatch[py_pickle.InstanceType] = save_exc_inst


if PY3:
    # In 3.x Unpickler is a class exposing find_class as an overridable, but it
    # cannot be overridden without subclassing.
    class _Unpickler(pickle.Unpickler):
        def find_class(self, module, func):
            return self.find_global(module, func)
    pickle__dumps = pickle.dumps
elif PY24:
    # On Python 2.4, we must use a pure-Python pickler.
    pickle__dumps = Py24Pickler.dumps
    _Unpickler = pickle.Unpickler
else:
    pickle__dumps = pickle.dumps
    # In 2.x Unpickler is a function exposing a writeable find_global
    # attribute.
    _Unpickler = pickle.Unpickler


class Message(object):
    """
    Messages are the fundamental unit of communication, comprising fields from
    the :ref:`stream-protocol` header, an optional reference to the receiving
    :class:`mitogen.core.Router` for ingress messages, and helper methods for
    deserialization and generating replies.
    """
    #: Integer target context ID. :class:`Router` delivers messages locally
    #: when their :attr:`dst_id` matches :data:`mitogen.context_id`, otherwise
    #: they are routed up or downstream.
    dst_id = None

    #: Integer source context ID. Used as the target of replies if any are
    #: generated.
    src_id = None

    #: Context ID under whose authority the message is acting. See
    #: :ref:`source-verification`.
    auth_id = None

    #: Integer target handle in the destination context. This is one of the
    #: :ref:`standard-handles`, or a dynamically generated handle used to
    #: receive a one-time reply, such as the return value of a function call.
    handle = None

    #: Integer target handle to direct any reply to this message. Used to
    #: receive a one-time reply, such as the return value of a function call.
    #: :data:`IS_DEAD` has a special meaning when it appears in this field.
    reply_to = None

    #: Raw message data bytes.
    data = b('')

    _unpickled = object()

    #: The :class:`Router` responsible for routing the message. This is
    #: :data:`None` for locally originated messages.
    router = None

    #: The :class:`Receiver` over which the message was last received. Part of
    #: the :class:`mitogen.select.Select` interface. Defaults to :data:`None`.
    receiver = None

    def __init__(self, **kwargs):
        """
        Construct a message from from the supplied `kwargs`. :attr:`src_id` and
        :attr:`auth_id` are always set to :data:`mitogen.context_id`.
        """
        self.src_id = mitogen.context_id
        self.auth_id = mitogen.context_id
        vars(self).update(kwargs)
        assert isinstance(self.data, BytesType)

    def _unpickle_context(self, context_id, name):
        return _unpickle_context(context_id, name, router=self.router)

    def _unpickle_sender(self, context_id, dst_handle):
        return _unpickle_sender(self.router, context_id, dst_handle)

    def _unpickle_bytes(self, s, encoding):
        s, n = LATIN1_CODEC.encode(s)
        return s

    def _find_global(self, module, func):
        """Return the class implementing `module_name.class_name` or raise
        `StreamError` if the module is not whitelisted."""
        if module == __name__:
            if func == '_unpickle_call_error' or func == 'CallError':
                return _unpickle_call_error
            elif func == '_unpickle_sender':
                return self._unpickle_sender
            elif func == '_unpickle_context':
                return self._unpickle_context
            elif func == 'Blob':
                return Blob
            elif func == 'Secret':
                return Secret
            elif func == 'Kwargs':
                return Kwargs
        elif module == '_codecs' and func == 'encode':
            return self._unpickle_bytes
        elif module == '__builtin__' and func == 'bytes':
            return BytesType
        raise StreamError('cannot unpickle %r/%r', module, func)

    @property
    def is_dead(self):
        """
        :data:`True` if :attr:`reply_to` is set to the magic value
        :data:`IS_DEAD`, indicating the sender considers the channel dead. Dead
        messages can be raised in a variety of circumstances, see
        :data:`IS_DEAD` for more information.
        """
        return self.reply_to == IS_DEAD

    @classmethod
    def dead(cls, reason=None, **kwargs):
        """
        Syntax helper to construct a dead message.
        """
        kwargs['data'] = (reason or u'').encode()
        return cls(reply_to=IS_DEAD, **kwargs)

    @classmethod
    def pickled(cls, obj, **kwargs):
        """
        Construct a pickled message, setting :attr:`data` to the serialization
        of `obj`, and setting remaining fields using `kwargs`.

        :returns:
            The new message.
        """
        self = cls(**kwargs)
        try:
            self.data = pickle__dumps(obj, protocol=2)
        except pickle.PicklingError:
            e = sys.exc_info()[1]
            self.data = pickle__dumps(CallError(e), protocol=2)
        return self

    def reply(self, msg, router=None, **kwargs):
        """
        Compose a reply to this message and send it using :attr:`router`, or
        `router` is :attr:`router` is :data:`None`.

        :param obj:
            Either a :class:`Message`, or an object to be serialized in order
            to construct a new message.
        :param router:
            Optional router to use if :attr:`router` is :data:`None`.
        :param kwargs:
            Optional keyword parameters overriding message fields in the reply.
        """
        if not isinstance(msg, Message):
            msg = Message.pickled(msg)
        msg.dst_id = self.src_id
        msg.handle = self.reply_to
        vars(msg).update(kwargs)
        if msg.handle:
            (self.router or router).route(msg)
        else:
            LOG.debug('Message.reply(): discarding due to zero handle: %r', msg)

    if PY3:
        UNPICKLER_KWARGS = {'encoding': 'bytes'}
    else:
        UNPICKLER_KWARGS = {}

    def _throw_dead(self):
        if len(self.data):
            raise ChannelError(self.data.decode('utf-8', 'replace'))
        elif self.src_id == mitogen.context_id:
            raise ChannelError(ChannelError.local_msg)
        else:
            raise ChannelError(ChannelError.remote_msg)

    def unpickle(self, throw=True, throw_dead=True):
        """
        Unpickle :attr:`data`, optionally raising any exceptions present.

        :param bool throw_dead:
            If :data:`True`, raise exceptions, otherwise it is the caller's
            responsibility.

        :raises CallError:
            The serialized data contained CallError exception.
        :raises ChannelError:
            The `is_dead` field was set.
        """
        _vv and IOLOG.debug('%r.unpickle()', self)
        if throw_dead and self.is_dead:
            self._throw_dead()

        obj = self._unpickled
        if obj is Message._unpickled:
            fp = BytesIO(self.data)
            unpickler = _Unpickler(fp, **self.UNPICKLER_KWARGS)
            unpickler.find_global = self._find_global
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
    """
    Senders are used to send pickled messages to a handle in another context,
    it is the inverse of :class:`mitogen.core.Receiver`.

    Senders may be serialized, making them convenient to wire up data flows.
    See :meth:`mitogen.core.Receiver.to_sender` for more information.

    :param Context context:
        Context to send messages to.
    :param int dst_handle:
        Destination handle to send messages to.
    """
    def __init__(self, context, dst_handle):
        self.context = context
        self.dst_handle = dst_handle

    def send(self, data):
        """
        Send `data` to the remote end.
        """
        _vv and IOLOG.debug('%r.send(%r..)', self, repr(data)[:100])
        self.context.send(Message.pickled(data, handle=self.dst_handle))

    explicit_close_msg = 'Sender was explicitly closed'

    def close(self):
        """
        Send a dead message to the remote, causing :meth:`ChannelError` to be
        raised in any waiting thread.
        """
        _vv and IOLOG.debug('%r.close()', self)
        self.context.send(
            Message.dead(
                reason=self.explicit_close_msg,
                handle=self.dst_handle
            )
        )

    def __repr__(self):
        return 'Sender(%r, %r)' % (self.context, self.dst_handle)

    def __reduce__(self):
        return _unpickle_sender, (self.context.context_id, self.dst_handle)


def _unpickle_sender(router, context_id, dst_handle):
    if not (isinstance(router, Router) and
            isinstance(context_id, (int, long)) and context_id >= 0 and
            isinstance(dst_handle, (int, long)) and dst_handle > 0):
        raise TypeError('cannot unpickle Sender: bad input')
    return Sender(Context(router, context_id), dst_handle)


class Receiver(object):
    """
    Receivers maintain a thread-safe queue of messages sent to a handle of this
    context from another context.

    :param mitogen.core.Router router:
        Router to register the handler on.

    :param int handle:
        If not :data:`None`, an explicit handle to register, otherwise an
        unused handle is chosen.

    :param bool persist:
        If :data:`False`, unregister the handler after one message is received.
        Single-message receivers are intended for RPC-like transactions, such
        as in the case of :meth:`mitogen.parent.Context.call_async`.

    :param mitogen.core.Context respondent:
        Context this receiver is receiving from. If not :data:`None`, arranges
        for the receiver to receive a dead message if messages can no longer be
        routed to the context due to disconnection, and ignores messages that
        did not originate from the respondent context.
    """
    #: If not :data:`None`, a reference to a function invoked as
    #: `notify(receiver)` when a new message is delivered to this receiver. The
    #: function is invoked on the broker thread, therefore it must not block.
    #: Used by :class:`mitogen.select.Select` to implement waiting on multiple
    #: receivers.
    notify = None

    raise_channelerror = True

    def __init__(self, router, handle=None, persist=True,
                 respondent=None, policy=None, overwrite=False):
        self.router = router
        #: The handle.
        self.handle = handle  # Avoid __repr__ crash in add_handler()
        self._latch = Latch()  # Must exist prior to .add_handler()
        self.handle = router.add_handler(
            fn=self._on_receive,
            handle=handle,
            policy=policy,
            persist=persist,
            respondent=respondent,
            overwrite=overwrite,
        )

    def __repr__(self):
        return 'Receiver(%r, %r)' % (self.router, self.handle)

    def __enter__(self):
        return self

    def __exit__(self, _1, _2, _3):
        self.close()

    def to_sender(self):
        """
        Return a :class:`Sender` configured to deliver messages to this
        receiver. As senders are serializable, this makes it convenient to pass
        `(context_id, handle)` pairs around::

            def deliver_monthly_report(sender):
                for line in open('monthly_report.txt'):
                    sender.send(line)
                sender.close()

            @mitogen.main()
            def main(router):
                remote = router.ssh(hostname='mainframe')
                recv = mitogen.core.Receiver(router)
                remote.call(deliver_monthly_report, recv.to_sender())
                for msg in recv:
                    print(msg)
        """
        return Sender(self.router.myself(), self.handle)

    def _on_receive(self, msg):
        """
        Callback registered for the handle with :class:`Router`; appends data
        to the internal queue.
        """
        _vv and IOLOG.debug('%r._on_receive(%r)', self, msg)
        self._latch.put(msg)
        if self.notify:
            self.notify(self)

    closed_msg = 'the Receiver has been closed'

    def close(self):
        """
        Unregister the receiver's handle from its associated router, and cause
        :class:`ChannelError` to be raised in any thread waiting in :meth:`get`
        on this receiver.
        """
        if self.handle:
            self.router.del_handler(self.handle)
            self.handle = None
        self._latch.close()

    def empty(self):
        """
        Return :data:`True` if calling :meth:`get` would block.

        As with :class:`Queue.Queue`, :data:`True` may be returned even though
        a subsequent call to :meth:`get` will succeed, since a message may be
        posted at any moment between :meth:`empty` and :meth:`get`.
        """
        return self._latch.empty()

    def get(self, timeout=None, block=True, throw_dead=True):
        """
        Sleep waiting for a message to arrive on this receiver.

        :param float timeout:
            If not :data:`None`, specifies a timeout in seconds.

        :raises mitogen.core.ChannelError:
            The remote end indicated the channel should be closed,
            communication with it was lost, or :meth:`close` was called in the
            local process.

        :raises mitogen.core.TimeoutError:
            Timeout was reached.

        :returns:
            :class:`Message` that was received.
        """
        _vv and IOLOG.debug('%r.get(timeout=%r, block=%r)', self, timeout, block)
        try:
            msg = self._latch.get(timeout=timeout, block=block)
        except LatchError:
            raise ChannelError(self.closed_msg)
        if msg.is_dead and throw_dead:
            msg._throw_dead()
        return msg

    def __iter__(self):
        """
        Yield consecutive :class:`Message` instances delivered to this receiver
        until :class:`ChannelError` is raised.
        """
        while True:
            try:
                msg = self.get()
            except ChannelError:
                return
            yield msg


class Channel(Sender, Receiver):
    """
    A channel inherits from :class:`mitogen.core.Sender` and
    `mitogen.core.Receiver` to provide bidirectional functionality.

    This class is incomplete and obsolete, it will be removed in Mitogen 0.3.
    Channels were an early attempt at syntax sugar. It is always easier to pass
    around unidirectional pairs of senders/receivers, even though the syntax is
    baroque:

    .. literalinclude:: ../examples/ping_pong.py

    Since all handles aren't known until after both ends are constructed, for
    both ends to communicate through a channel, it is necessary for one end to
    retrieve the handle allocated to the other and reconfigure its own channel
    to match. Currently this is a manual task.
    """
    def __init__(self, router, context, dst_handle, handle=None):
        Sender.__init__(self, context, dst_handle)
        Receiver.__init__(self, router, handle)

    def close(self):
        Receiver.close(self)
        Sender.close(self)

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
    # The Mitogen package is handled specially, since the child context must
    # construct it manually during startup.
    MITOGEN_PKG_CONTENT = [
        'compat',
        'debug',
        'doas',
        'docker',
        'kubectl',
        'fakessh',
        'fork',
        'jail',
        'lxc',
        'lxd',
        'master',
        'minify',
        'parent',
        'select',
        'service',
        'setns',
        'ssh',
        'su',
        'sudo',
        'utils',
    ]

    ALWAYS_BLACKLIST = [
        # 2.x generates needless imports for 'builtins', while 3.x does the
        # same for '__builtin__'. The correct one is built-in, the other always
        # a negative round-trip.
        'builtins',
        '__builtin__',
        'thread',

        # org.python.core imported by copy, pickle, xml.sax; breaks Jython, but
        # very unlikely to trigger a bug report.
        'org',
    ]

    if PY3:
        ALWAYS_BLACKLIST += ['cStringIO']

    def __init__(self, router, context, core_src, whitelist=(), blacklist=()):
        self._context = context
        self._present = {'mitogen': self.MITOGEN_PKG_CONTENT}
        self._lock = threading.Lock()
        self.whitelist = list(whitelist) or ['']
        self.blacklist = list(blacklist) + self.ALWAYS_BLACKLIST

        # Preserve copies of the original server-supplied whitelist/blacklist
        # for later use by children.
        self.master_whitelist = self.whitelist[:]
        self.master_blacklist = self.blacklist[:]

        # Presence of an entry in this map indicates in-flight GET_MODULE.
        self._callbacks = {}
        self._cache = {}
        if core_src:
            self._update_linecache('x/mitogen/core.py', core_src)
            self._cache['mitogen.core'] = (
                'mitogen.core',
                None,
                'x/mitogen/core.py',
                zlib.compress(core_src, 9),
                [],
            )
        self._install_handler(router)

    def _update_linecache(self, path, data):
        """
        The Python 2.4 linecache module, used to fetch source code for
        tracebacks and :func:`inspect.getsource`, does not support PEP-302,
        meaning it needs extra help to for Mitogen-loaded modules. Directly
        populate its cache if a loaded module belongs to the Mitogen package.
        """
        if PY24 and 'mitogen' in path:
            linecache.cache[path] = (
                len(data),
                0.0,
                [line+'\n' for line in data.splitlines()],
                path,
            )

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
            raise ModuleNotFoundError()

        parent, _, modname = str_rpartition(fullname, '.')
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
        try:
            _v and LOG.debug('%r.find_module(%r)', self, fullname)
            fullname = to_text(fullname)
            pkgname, dot, _ = str_rpartition(fullname, '.')
            pkg = sys.modules.get(pkgname)
            if pkgname and getattr(pkg, '__loader__', None) is not self:
                LOG.debug('%r: %r is submodule of a package we did not load',
                          self, fullname)
                return None

            suffix = fullname[len(pkgname+dot):]
            if pkgname and suffix not in self._present.get(pkgname, ()):
                LOG.debug('%r: master doesn\'t know %r', self, fullname)
                return None

            # #114: explicitly whitelisted prefixes override any
            # system-installed package.
            if self.whitelist != ['']:
                if any(fullname.startswith(s) for s in self.whitelist):
                    return self

            try:
                self.builtin_find_module(fullname)
                _vv and IOLOG.debug('%r: %r is available locally',
                                    self, fullname)
            except ImportError:
                _vv and IOLOG.debug('find_module(%r) returning self', fullname)
                return self
        finally:
            del _tls.running

    blacklisted_msg = (
        '%r is present in the Mitogen importer blacklist, therefore this '
        'context will not attempt to request it from the master, as the '
        'request will always be refused.'
    )
    pkg_resources_msg = (
        'pkg_resources is prohibited from importing __main__, as it causes '
        'problems in applications whose main module is not designed to be '
        're-imported by children.'
    )
    absent_msg = (
        'The Mitogen master process was unable to serve %r. It may be a '
        'native Python extension, or it may be missing entirely. Check the '
        'importer debug logs on the master for more information.'
    )

    def _refuse_imports(self, fullname):
        if is_blacklisted_import(self, fullname):
            raise ModuleNotFoundError(self.blacklisted_msg % (fullname,))

        f = sys._getframe(2)
        requestee = f.f_globals['__name__']

        if fullname == '__main__' and requestee == 'pkg_resources':
            # Anything that imports pkg_resources will eventually cause
            # pkg_resources to try and scan __main__ for its __requires__
            # attribute (pkg_resources/__init__.py::_build_master()). This
            # breaks any app that is not expecting its __main__ to suddenly be
            # sucked over a network and injected into a remote process, like
            # py.test.
            raise ModuleNotFoundError(self.pkg_resources_msg)

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
            if tup[2] is not None and PY24:
                self._update_linecache(
                    path='master:' + tup[2],
                    data=zlib.decompress(tup[3])
                )
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
                    self._context.send(
                        Message(data=b(fullname), handle=GET_MODULE)
                    )
        finally:
            self._lock.release()

        if present:
            callback()

    def load_module(self, fullname):
        fullname = to_text(fullname)
        _v and LOG.debug('Importer.load_module(%r)', fullname)
        self._refuse_imports(fullname)

        event = threading.Event()
        self._request_module(fullname, event.set)
        event.wait()

        ret = self._cache[fullname]
        if ret[2] is None:
            raise ModuleNotFoundError(self.absent_msg % (fullname,))

        pkg_present = ret[1]
        mod = sys.modules.setdefault(fullname, imp.new_module(fullname))
        mod.__file__ = self.get_filename(fullname)
        mod.__loader__ = self
        if pkg_present is not None:  # it's a package.
            mod.__path__ = []
            mod.__package__ = fullname
            self._present[fullname] = pkg_present
        else:
            mod.__package__ = str_rpartition(fullname, '.')[0] or None

        if mod.__package__ and not PY3:
            # 2.x requires __package__ to be exactly a string.
            mod.__package__ = mod.__package__.encode()

        source = self.get_source(fullname)
        try:
            code = compile(source, mod.__file__, 'exec', 0, 1)
        except SyntaxError:
            LOG.exception('while importing %r', fullname)
            raise

        if PY3:
            exec(code, vars(mod))
        else:
            exec('exec code in vars(mod)')
        return mod

    def get_filename(self, fullname):
        if fullname in self._cache:
            path = self._cache[fullname][2]
            if path is None:
                # If find_loader() returns self but a subsequent master RPC
                # reveals the module can't be loaded, and so load_module()
                # throws ImportError, on Python 3.x it is still possible for
                # the loader to be called to fetch metadata.
                raise ModuleNotFoundError(self.absent_msg % (fullname,))
            return u'master:' + self._cache[fullname][2]

    def get_source(self, fullname):
        if fullname in self._cache:
            compressed = self._cache[fullname][3]
            if compressed is None:
                raise ModuleNotFoundError(self.absent_msg % (fullname,))

            source = zlib.decompress(self._cache[fullname][3])
            if PY3:
                return to_text(source)
            return source


class LogHandler(logging.Handler):
    def __init__(self, context):
        logging.Handler.__init__(self)
        self.context = context
        self.local = threading.local()
        self._buffer = []

    def uncork(self):
        """
        #305: during startup :class:`LogHandler` may be installed before it is
        possible to route messages, therefore messages are buffered until
        :meth:`uncork` is called by :class:`ExternalContext`.
        """
        self._send = self.context.send
        for msg in self._buffer:
            self._send(msg)
        self._buffer = None

    def _send(self, msg):
        self._buffer.append(msg)

    def emit(self, rec):
        if rec.name == 'mitogen.io' or \
           getattr(self.local, 'in_emit', False):
            return

        self.local.in_emit = True
        try:
            msg = self.format(rec)
            encoded = '%s\x00%s\x00%s' % (rec.name, rec.levelno, msg)
            if isinstance(encoded, UnicodeType):
                # Logging package emits both :(
                encoded = encoded.encode('utf-8')
            self._send(Message(data=encoded, handle=FORWARD_LOG))
        finally:
            self.local.in_emit = False


class Side(object):
    """
    Represent a single side of a :class:`BasicStream`. This exists to allow
    streams implemented using unidirectional (e.g. UNIX pipe) and bidirectional
    (e.g. UNIX socket) file descriptors to operate identically.

    :param mitogen.core.Stream stream:
        The stream this side is associated with.

    :param int fd:
        Underlying file descriptor.

    :param bool keep_alive:
        Value for :attr:`keep_alive`

    During construction, the file descriptor has its :data:`os.O_NONBLOCK` flag
    enabled using :func:`fcntl.fcntl`.
    """
    _fork_refs = weakref.WeakValueDictionary()

    def __init__(self, stream, fd, cloexec=True, keep_alive=True, blocking=False):
        #: The :class:`Stream` for which this is a read or write side.
        self.stream = stream
        #: Integer file descriptor to perform IO on, or :data:`None` if
        #: :meth:`close` has been called.
        self.fd = fd
        self.closed = False
        #: If :data:`True`, causes presence of this side in
        #: :class:`Broker`'s active reader set to defer shutdown until the
        #: side is disconnected.
        self.keep_alive = keep_alive
        self._fork_refs[id(self)] = self
        if cloexec:
            set_cloexec(fd)
        if not blocking:
            set_nonblock(fd)

    def __repr__(self):
        return '<Side of %r fd %s>' % (self.stream, self.fd)

    @classmethod
    def _on_fork(cls):
        while cls._fork_refs:
            _, side = cls._fork_refs.popitem()
            _vv and IOLOG.debug('Side._on_fork() closing %r', side)
            side.close()

    def close(self):
        """
        Call :func:`os.close` on :attr:`fd` if it is not :data:`None`,
        then set it to :data:`None`.
        """
        if not self.closed:
            _vv and IOLOG.debug('%r.close()', self)
            self.closed = True
            os.close(self.fd)

    def read(self, n=CHUNK_SIZE):
        """
        Read up to `n` bytes from the file descriptor, wrapping the underlying
        :func:`os.read` call with :func:`io_op` to trap common disconnection
        conditions.

        :meth:`read` always behaves as if it is reading from a regular UNIX
        file; socket, pipe, and TTY disconnection errors are masked and result
        in a 0-sized read like a regular file.

        :returns:
            Bytes read, or the empty to string to indicate disconnection was
            detected.
        """
        if self.closed:
            # Refuse to touch the handle after closed, it may have been reused
            # by another thread. TODO: synchronize read()/write()/close().
            return b('')
        s, disconnected = io_op(os.read, self.fd, n)
        if disconnected:
            LOG.debug('%r.read(): disconnected: %s', self, disconnected)
            return b('')
        return s

    def write(self, s):
        """
        Write as much of the bytes from `s` as possible to the file descriptor,
        wrapping the underlying :func:`os.write` call with :func:`io_op` to
        trap common disconnection conditions.

        :returns:
            Number of bytes written, or :data:`None` if disconnection was
            detected.
        """
        if self.closed or self.fd is None:
            # Refuse to touch the handle after closed, it may have been reused
            # by another thread.
            return None

        written, disconnected = io_op(os.write, self.fd, s)
        if disconnected:
            LOG.debug('%r.write(): disconnected: %s', self, disconnected)
            return None
        return written


class BasicStream(object):
    #: A :class:`Side` representing the stream's receive file descriptor.
    receive_side = None

    #: A :class:`Side` representing the stream's transmit file descriptor.
    transmit_side = None

    def on_receive(self, broker):
        """
        Called by :class:`Broker` when the stream's :attr:`receive_side` has
        been marked readable using :meth:`Broker.start_receive` and the broker
        has detected the associated file descriptor is ready for reading.

        Subclasses must implement this if :meth:`Broker.start_receive` is ever
        called on them, and the method must call :meth:`on_disconect` if
        reading produces an empty string.
        """
        pass

    def on_transmit(self, broker):
        """
        Called by :class:`Broker` when the stream's :attr:`transmit_side`
        has been marked writeable using :meth:`Broker._start_transmit` and
        the broker has detected the associated file descriptor is ready for
        writing.

        Subclasses must implement this if :meth:`Broker._start_transmit` is
        ever called on them.
        """
        pass

    def on_shutdown(self, broker):
        """
        Called by :meth:`Broker.shutdown` to allow the stream time to
        gracefully shutdown. The base implementation simply called
        :meth:`on_disconnect`.
        """
        _v and LOG.debug('%r.on_shutdown()', self)
        fire(self, 'shutdown')
        self.on_disconnect(broker)

    def on_disconnect(self, broker):
        """
        Called by :class:`Broker` to force disconnect the stream. The base
        implementation simply closes :attr:`receive_side` and
        :attr:`transmit_side` and unregisters the stream from the broker.
        """
        LOG.debug('%r.on_disconnect()', self)
        if self.receive_side:
            broker.stop_receive(self)
            self.receive_side.close()
        if self.transmit_side:
            broker._stop_transmit(self)
            self.transmit_side.close()
        fire(self, 'disconnect')


class Stream(BasicStream):
    """
    :class:`BasicStream` subclass implementing mitogen's :ref:`stream
    protocol <stream-protocol>`.
    """
    #: If not :data:`None`, :class:`Router` stamps this into
    #: :attr:`Message.auth_id` of every message received on this stream.
    auth_id = None

    #: If not :data:`False`, indicates the stream has :attr:`auth_id` set and
    #: its value is the same as :data:`mitogen.context_id` or appears in
    #: :data:`mitogen.parent_ids`.
    is_privileged = False

    def __init__(self, router, remote_id, **kwargs):
        self._router = router
        self.remote_id = remote_id
        self.name = u'default'
        self.sent_modules = set(['mitogen', 'mitogen.core'])
        self.construct(**kwargs)
        self._input_buf = collections.deque()
        self._output_buf = collections.deque()
        self._input_buf_len = 0
        self._output_buf_len = 0
        #: Routing records the dst_id of every message arriving from this
        #: stream. Any arriving DEL_ROUTE is rebroadcast for any such ID.
        self.egress_ids = set()

    def construct(self):
        pass

    def _internal_receive(self, broker, buf):
        if self._input_buf and self._input_buf_len < 128:
            self._input_buf[0] += buf
        else:
            self._input_buf.append(buf)

        self._input_buf_len += len(buf)
        while self._receive_one(broker):
            pass

    def on_receive(self, broker):
        """Handle the next complete message on the stream. Raise
        :class:`StreamError` on failure."""
        _vv and IOLOG.debug('%r.on_receive()', self)

        buf = self.receive_side.read()
        if not buf:
            return self.on_disconnect(broker)

        self._internal_receive(broker, buf)

    HEADER_FMT = '>hLLLLLL'
    HEADER_LEN = struct.calcsize(HEADER_FMT)
    HEADER_MAGIC = 0x4d49  # 'MI'

    corrupt_msg = (
        'Corruption detected: frame signature incorrect. This likely means '
        'some external process is interfering with the connection. Received:'
        '\n\n'
        '%r'
    )

    def _receive_one(self, broker):
        if self._input_buf_len < self.HEADER_LEN:
            return False

        msg = Message()
        msg.router = self._router
        (magic, msg.dst_id, msg.src_id, msg.auth_id,
         msg.handle, msg.reply_to, msg_len) = struct.unpack(
            self.HEADER_FMT,
            self._input_buf[0][:self.HEADER_LEN],
        )

        if magic != self.HEADER_MAGIC:
            LOG.error(self.corrupt_msg, self._input_buf[0][:2048])
            self.on_disconnect(broker)
            return False

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

        msg.data = b('').join(bits)
        self._input_buf.appendleft(buf[prev_start+len(bit):])
        self._input_buf_len -= total_len
        self._router._async_route(msg, self)
        return True

    def pending_bytes(self):
        """
        Return the number of bytes queued for transmission on this stream. This
        can be used to limit the amount of data buffered in RAM by an otherwise
        unlimited consumer.

        For an accurate result, this method should be called from the Broker
        thread, for example by using :meth:`Broker.defer_sync`.
        """
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
                self._output_buf.appendleft(BufferType(buf, written))

            _vv and IOLOG.debug('%r.on_transmit() -> len %d', self, written)
            self._output_buf_len -= written

        if not self._output_buf:
            broker._stop_transmit(self)

    def _send(self, msg):
        _vv and IOLOG.debug('%r._send(%r)', self, msg)
        pkt = struct.pack(self.HEADER_FMT, self.HEADER_MAGIC, msg.dst_id,
                          msg.src_id, msg.auth_id, msg.handle,
                          msg.reply_to or 0, len(msg.data)) + msg.data

        if not self._output_buf_len:
            # Modifying epoll/Kqueue state is expensive, as are needless broker
            # loops. Rather than wait for writeability, just write immediately,
            # and fall back to the broker loop on error or full buffer.
            try:
                n = self.transmit_side.write(pkt)
                if n:
                    if n == len(pkt):
                        return
                    pkt = pkt[n:]
            except OSError:
                pass

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
        return "%s.%s('%s')" % (cls.__module__, cls.__name__, self.name)


class Context(object):
    """
    Represent a remote context regardless of the underlying connection method.
    Context objects are simple facades that emit messages through an
    associated router, and have :ref:`signals` raised against them in response
    to various events relating to the context.

    **Note:** This is the somewhat limited core version, used by child
    contexts. The master subclass is documented below this one.

    Contexts maintain no internal state and are thread-safe.

    Prefer :meth:`Router.context_by_id` over constructing context objects
    explicitly, as that method is deduplicating, and returns the only context
    instance :ref:`signals` will be raised on.

    :param Router router:
        Router to emit messages through.
    :param int context_id:
        Context ID.
    :param str name:
        Context name.
    """
    remote_name = None

    def __init__(self, router, context_id, name=None):
        self.router = router
        self.context_id = context_id
        self.name = name

    def __reduce__(self):
        name = self.name
        if name and not isinstance(name, UnicodeType):
            name = UnicodeType(name, 'utf-8')
        return _unpickle_context, (self.context_id, name)

    def on_disconnect(self):
        _v and LOG.debug('%r.on_disconnect()', self)
        fire(self, 'disconnect')

    def send_async(self, msg, persist=False):
        """
        Arrange for `msg` to be delivered to this context, with replies
        directed to a newly constructed receiver. :attr:`dst_id
        <Message.dst_id>` is set to the target context ID, and :attr:`reply_to
        <Message.reply_to>` is set to the newly constructed receiver's handle.

        :param bool persist:
            If :data:`False`, the handler will be unregistered after a single
            message has been received.

        :param mitogen.core.Message msg:
            The message.

        :returns:
            :class:`Receiver` configured to receive any replies sent to the
            message's `reply_to` handle.
        """
        if self.router.broker._thread == threading.currentThread():  # TODO
            raise SystemError('Cannot making blocking call on broker thread')

        receiver = Receiver(self.router, persist=persist, respondent=self)
        msg.dst_id = self.context_id
        msg.reply_to = receiver.handle

        _v and LOG.debug('%r.send_async(%r)', self, msg)
        self.send(msg)
        return receiver

    def call_service_async(self, service_name, method_name, **kwargs):
        _v and LOG.debug('%r.call_service_async(%r, %r, %r)',
                         self, service_name, method_name, kwargs)
        if isinstance(service_name, BytesType):
            service_name = service_name.encode('utf-8')
        elif not isinstance(service_name, UnicodeType):
            service_name = service_name.name()  # Service.name()
        tup = (service_name, to_text(method_name), Kwargs(kwargs))
        msg = Message.pickled(tup, handle=CALL_SERVICE)
        return self.send_async(msg)

    def send(self, msg):
        """
        Arrange for `msg` to be delivered to this context. :attr:`dst_id
        <Message.dst_id>` is set to the target context ID.

        :param Message msg:
            Message.
        """
        msg.dst_id = self.context_id
        self.router.route(msg)

    def call_service(self, service_name, method_name, **kwargs):
        recv = self.call_service_async(service_name, method_name, **kwargs)
        return recv.get().unpickle()

    def send_await(self, msg, deadline=None):
        """
        Like :meth:`send_async`, but expect a single reply (`persist=False`)
        delivered within `deadline` seconds.

        :param mitogen.core.Message msg:
            The message.
        :param float deadline:
            If not :data:`None`, seconds before timing out waiting for a reply.
        :returns:
            Deserialized reply.
        :raises TimeoutError:
            No message was received and `deadline` passed.
        """
        receiver = self.send_async(msg)
        response = receiver.get(deadline)
        data = response.unpickle()
        _vv and IOLOG.debug('%r._send_await() -> %r', self, data)
        return data

    def __repr__(self):
        return 'Context(%s, %r)' % (self.context_id, self.name)


def _unpickle_context(context_id, name, router=None):
    if not (isinstance(context_id, (int, long)) and context_id >= 0 and (
        (name is None) or
        (isinstance(name, UnicodeType) and len(name) < 100))
    ):
        raise TypeError('cannot unpickle Context: bad input')

    if isinstance(router, Router):
        return router.context_by_id(context_id, name=name)
    return Context(None, context_id, name)  # For plain Jane pickle.


class Poller(object):
    """
    A poller manages OS file descriptors the user is waiting to become
    available for IO. The :meth:`poll` method blocks the calling thread
    until one or more become ready. The default implementation is based on
    :func:`select.poll`.

    Each descriptor has an associated `data` element, which is unique for each
    readiness type, and defaults to being the same as the file descriptor. The
    :meth:`poll` method yields the data associated with a descriptor, rather
    than the descriptor itself, allowing concise loops like::

        p = Poller()
        p.start_receive(conn.fd, data=conn.on_read)
        p.start_transmit(conn.fd, data=conn.on_write)

        for callback in p.poll():
            callback()  # invoke appropriate bound instance method

    Pollers may be modified while :meth:`poll` is yielding results. Removals
    are processed immediately, causing pending events for the descriptor to be
    discarded.

    The :meth:`close` method must be called when a poller is discarded to avoid
    a resource leak.

    Pollers may only be used by one thread at a time.
    """
    # This changed from select() to poll() in Mitogen 0.2.4. Since poll() has
    # no upper FD limit, it is suitable for use with Latch, which must handle
    # FDs larger than select's limit during many-host runs. We want this
    # because poll() requires no setup and teardown: just a single system call,
    # which is important because Latch.get() creates a Poller on each
    # invocation. In a microbenchmark, poll() vs. epoll_ctl() is 30% faster in
    # this scenario. If select() must return in future, it is important
    # Latch.poller_class is set from parent.py to point to the industrial
    # strength poller for the OS, otherwise Latch will fail randomly.

    #: Increments on every poll(). Used to version _rfds and _wfds.
    _generation = 1

    def __init__(self):
        self._rfds = {}
        self._wfds = {}
        self._pollobj = select.poll()

    def __repr__(self):
        return '%s(%#x)' % (type(self).__name__, id(self))

    @property
    def readers(self):
        """
        Return a list of `(fd, data)` tuples for every FD registered for
        receive readiness.
        """
        return list((fd, data) for fd, (data, gen) in self._rfds.items())

    @property
    def writers(self):
        """
        Return a list of `(fd, data)` tuples for every FD registered for
        transmit readiness.
        """
        return list((fd, data) for fd, (data, gen) in self._wfds.items())

    def close(self):
        """
        Close any underlying OS resource used by the poller.
        """
        pass

    _readmask = select.POLLIN | select.POLLHUP
    # TODO: no proof we dont need writemask too

    def _update(self, fd):
        mask = (((fd in self._rfds) and self._readmask) |
                ((fd in self._wfds) and select.POLLOUT))
        if mask:
            self._pollobj.register(fd, mask)
        else:
            try:
                self._pollobj.unregister(fd)
            except KeyError:
                pass

    def start_receive(self, fd, data=None):
        """
        Cause :meth:`poll` to yield `data` when `fd` is readable.
        """
        self._rfds[fd] = (data or fd, self._generation)
        self._update(fd)

    def stop_receive(self, fd):
        """
        Stop yielding readability events for `fd`.

        Redundant calls to :meth:`stop_receive` are silently ignored, this may
        change in future.
        """
        self._rfds.pop(fd, None)
        self._update(fd)

    def start_transmit(self, fd, data=None):
        """
        Cause :meth:`poll` to yield `data` when `fd` is writeable.
        """
        self._wfds[fd] = (data or fd, self._generation)
        self._update(fd)

    def stop_transmit(self, fd):
        """
        Stop yielding writeability events for `fd`.

        Redundant calls to :meth:`stop_transmit` are silently ignored, this may
        change in future.
        """
        self._wfds.pop(fd, None)
        self._update(fd)

    def _poll(self, timeout):
        if timeout:
            timeout *= 1000

        events, _ = io_op(self._pollobj.poll, timeout)
        for fd, event in events:
            if event & self._readmask:
                _vv and IOLOG.debug('%r: POLLIN|POLLHUP for %r', self, fd)
                data, gen = self._rfds.get(fd, (None, None))
                if gen and gen < self._generation:
                    yield data
            if event & select.POLLOUT:
                _vv and IOLOG.debug('%r: POLLOUT for %r', self, fd)
                data, gen = self._wfds.get(fd, (None, None))
                if gen and gen < self._generation:
                    yield data

    def poll(self, timeout=None):
        """
        Block the calling thread until one or more FDs are ready for IO.

        :param float timeout:
            If not :data:`None`, seconds to wait without an event before
            returning an empty iterable.
        :returns:
            Iterable of `data` elements associated with ready FDs.
        """
        _vv and IOLOG.debug('%r.poll(%r)', self, timeout)
        self._generation += 1
        return self._poll(timeout)


class Latch(object):
    """
    A latch is a :class:`Queue.Queue`-like object that supports mutation and
    waiting from multiple threads, however unlike :class:`Queue.Queue`,
    waiting threads always remain interruptible, so CTRL+C always succeeds, and
    waits where a timeout is set experience no wake up latency. These
    properties are not possible in combination using the built-in threading
    primitives available in Python 2.x.

    Latches implement queues using the UNIX self-pipe trick, and a per-thread
    :func:`socket.socketpair` that is lazily created the first time any
    latch attempts to sleep on a thread, and dynamically associated with the
    waiting Latch only for duration of the wait.

    See :ref:`waking-sleeping-threads` for further discussion.
    """
    poller_class = Poller

    # The _cls_ prefixes here are to make it crystal clear in the code which
    # state mutation isn't covered by :attr:`_lock`.

    #: List of reusable :func:`socket.socketpair` tuples. The list is mutated
    #: from multiple threads, the only safe operations are `append()` and
    #: `pop()`.
    _cls_idle_socketpairs = []

    #: List of every socket object that must be closed by :meth:`_on_fork`.
    #: Inherited descriptors cannot be reused, as the duplicated handles
    #: reference the same underlying kernel object in use by the parent.
    _cls_all_sockets = []

    def __init__(self):
        self.closed = False
        self._lock = threading.Lock()
        #: List of unconsumed enqueued items.
        self._queue = []
        #: List of `(wsock, cookie)` awaiting an element, where `wsock` is the
        #: socketpair's write side, and `cookie` is the string to write.
        self._sleeping = []
        #: Number of elements of :attr:`_sleeping` that have already been
        #: woken, and have a corresponding element index from :attr:`_queue`
        #: assigned to them.
        self._waking = 0

    @classmethod
    def _on_fork(cls):
        """
        Clean up any files belonging to the parent process after a fork.
        """
        cls._cls_idle_socketpairs = []
        while cls._cls_all_sockets:
            cls._cls_all_sockets.pop().close()

    def close(self):
        """
        Mark the latch as closed, and cause every sleeping thread to be woken,
        with :class:`mitogen.core.LatchError` raised in each thread.
        """
        self._lock.acquire()
        try:
            self.closed = True
            while self._waking < len(self._sleeping):
                wsock, cookie = self._sleeping[self._waking]
                self._wake(wsock, cookie)
                self._waking += 1
        finally:
            self._lock.release()

    def empty(self):
        """
        Return :data:`True` if calling :meth:`get` would block.

        As with :class:`Queue.Queue`, :data:`True` may be returned even
        though a subsequent call to :meth:`get` will succeed, since a
        message may be posted at any moment between :meth:`empty` and
        :meth:`get`.

        As with :class:`Queue.Queue`, :data:`False` may be returned even
        though a subsequent call to :meth:`get` will block, since another
        waiting thread may be woken at any moment between :meth:`empty` and
        :meth:`get`.

        :raises LatchError:
            The latch has already been marked closed.
        """
        self._lock.acquire()
        try:
            if self.closed:
                raise LatchError()
            return len(self._queue) == 0
        finally:
            self._lock.release()

    def _get_socketpair(self):
        """
        Return an unused socketpair, creating one if none exist.
        """
        try:
            return self._cls_idle_socketpairs.pop()  # pop() must be atomic
        except IndexError:
            rsock, wsock = socket.socketpair()
            set_cloexec(rsock.fileno())
            set_cloexec(wsock.fileno())
            self._cls_all_sockets.extend((rsock, wsock))
            return rsock, wsock

    COOKIE_MAGIC, = struct.unpack('L', b('LTCH') * (struct.calcsize('L')//4))
    COOKIE_FMT = 'Llll'
    COOKIE_SIZE = struct.calcsize(COOKIE_FMT)

    def _make_cookie(self):
        """
        Return a string encoding the ID of the process, instance and thread.
        This disambiguates legitimate wake-ups, accidental writes to the FD,
        and buggy internal FD sharing.
        """
        return struct.pack(self.COOKIE_FMT, self.COOKIE_MAGIC,
                           os.getpid(), id(self), thread.get_ident())

    def get(self, timeout=None, block=True):
        """
        Return the next enqueued object, or sleep waiting for one.

        :param float timeout:
            If not :data:`None`, specifies a timeout in seconds.

        :param bool block:
            If :data:`False`, immediately raise
            :class:`mitogen.core.TimeoutError` if the latch is empty.

        :raises mitogen.core.LatchError:
            :meth:`close` has been called, and the object is no longer valid.

        :raises mitogen.core.TimeoutError:
            Timeout was reached.

        :returns:
            The de-queued object.
        """
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
            rsock, wsock = self._get_socketpair()
            cookie = self._make_cookie()
            self._sleeping.append((wsock, cookie))
        finally:
            self._lock.release()

        poller = self.poller_class()
        poller.start_receive(rsock.fileno())
        try:
            return self._get_sleep(poller, timeout, block, rsock, wsock, cookie)
        finally:
            poller.close()

    def _get_sleep(self, poller, timeout, block, rsock, wsock, cookie):
        """
        When a result is not immediately available, sleep waiting for
        :meth:`put` to write a byte to our socket pair.
        """
        _vv and IOLOG.debug(
            '%r._get_sleep(timeout=%r, block=%r, rfd=%d, wfd=%d)',
            self, timeout, block, rsock.fileno(), wsock.fileno()
        )

        e = None
        woken = None
        try:
            woken = list(poller.poll(timeout))
        except Exception:
            e = sys.exc_info()[1]

        self._lock.acquire()
        try:
            i = self._sleeping.index((wsock, cookie))
            del self._sleeping[i]
            if not woken:
                raise e or TimeoutError()

            got_cookie = rsock.recv(self.COOKIE_SIZE)
            self._cls_idle_socketpairs.append((rsock, wsock))

            assert cookie == got_cookie, (
                "Cookie incorrect; got %r, expected %r" \
                % (binascii.hexlify(got_cookie),
                   binascii.hexlify(cookie))
            )
            assert i < self._waking, (
                "Cookie correct, but no queue element assigned."
            )
            self._waking -= 1
            if self.closed:
                raise LatchError()
            _vv and IOLOG.debug('%r.get() wake -> %r', self, self._queue[i])
            return self._queue.pop(i)
        finally:
            self._lock.release()

    def put(self, obj):
        """
        Enqueue an object, waking the first thread waiting for a result, if one
        exists.

        :raises mitogen.core.LatchError:
            :meth:`close` has been called, and the object is no longer valid.
        """
        _vv and IOLOG.debug('%r.put(%r)', self, obj)
        self._lock.acquire()
        try:
            if self.closed:
                raise LatchError()
            self._queue.append(obj)

            if self._waking < len(self._sleeping):
                wsock, cookie = self._sleeping[self._waking]
                self._waking += 1
                _vv and IOLOG.debug('%r.put() -> waking wfd=%r',
                                    self, wsock.fileno())
                self._wake(wsock, cookie)
        finally:
            self._lock.release()

    def _wake(self, wsock, cookie):
        written, disconnected = io_op(os.write, wsock.fileno(), cookie)
        assert written == len(cookie) and not disconnected

    def __repr__(self):
        return 'Latch(%#x, size=%d, t=%r)' % (
            id(self),
            len(self._queue),
            threading.currentThread().getName(),
        )


class Waker(BasicStream):
    """
    :class:`BasicStream` subclass implementing the `UNIX self-pipe trick`_.
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
            self.receive_side and self.receive_side.fd,
            self.transmit_side and self.transmit_side.fd,
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
        Drain the pipe and fire callbacks. Since :attr:`_deferred` is
        synchronized, :meth:`defer` and :meth:`on_receive` can conspire to
        ensure only one byte needs to be pending regardless of queue length.
        """
        _vv and IOLOG.debug('%r.on_receive()', self)
        self._lock.acquire()
        try:
            self.receive_side.read(1)
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

    def _wake(self):
        """
        Wake the multiplexer by writing a byte. If Broker is midway through
        teardown, the FD may already be closed, so ignore EBADF.
        """
        try:
            self.transmit_side.write(b(' '))
        except OSError:
            e = sys.exc_info()[1]
            if e.args[0] != errno.EBADF:
                raise

    broker_shutdown_msg = (
        "An attempt was made to enqueue a message with a Broker that has "
        "already exitted. It is likely your program called Broker.shutdown() "
        "too early."
    )

    def defer(self, func, *args, **kwargs):
        """
        Arrange for `func()` to execute on the broker thread. This function
        returns immediately without waiting the result of `func()`. Use
        :meth:`defer_sync` to block until a result is available.

        :raises mitogen.core.Error:
            :meth:`defer` was called after :class:`Broker` has begun shutdown.
        """
        if thread.get_ident() == self.broker_ident:
            _vv and IOLOG.debug('%r.defer() [immediate]', self)
            return func(*args, **kwargs)
        if self._broker._exitted:
            raise Error(self.broker_shutdown_msg)

        _vv and IOLOG.debug('%r.defer() [fd=%r]', self, self.transmit_side.fd)
        self._lock.acquire()
        try:
            if not self._deferred:
                self._wake()
            self._deferred.append((func, args, kwargs))
        finally:
            self._lock.release()


class IoLogger(BasicStream):
    """
    :class:`BasicStream` subclass that sets up redirection of a standard
    UNIX file descriptor back into the Python :mod:`logging` package.
    """
    _buf = ''

    def __init__(self, broker, name, dest_fd):
        self._broker = broker
        self._name = name
        self._rsock, self._wsock = socket.socketpair()
        os.dup2(self._wsock.fileno(), dest_fd)
        set_cloexec(self._wsock.fileno())

        self._log = logging.getLogger(name)
        # #453: prevent accidental log initialization in a child creating a
        # feedback loop.
        self._log.propagate = False
        self._log.handlers = logging.getLogger().handlers[:]

        self.receive_side = Side(self, self._rsock.fileno())
        self.transmit_side = Side(self, dest_fd, cloexec=False, blocking=True)
        self._broker.start_receive(self)

    def __repr__(self):
        return '<IoLogger %s>' % (self._name,)

    def _log_lines(self):
        while self._buf.find('\n') != -1:
            line, _, self._buf = str_partition(self._buf, '\n')
            self._log.info('%s', line.rstrip('\n'))

    def on_shutdown(self, broker):
        """Shut down the write end of the logging socket."""
        _v and LOG.debug('%r.on_shutdown()', self)
        if not IS_WSL:
            # #333: WSL generates invalid readiness indication on shutdown()
            self._wsock.shutdown(socket.SHUT_WR)
        self._wsock.close()
        self.transmit_side.close()

    def on_receive(self, broker):
        _vv and IOLOG.debug('%r.on_receive()', self)
        buf = self.receive_side.read()
        if not buf:
            return self.on_disconnect(broker)

        self._buf += buf.decode('latin1')
        self._log_lines()


class Router(object):
    """
    Route messages between contexts, and invoke local handlers for messages
    addressed to this context. :meth:`Router.route() <route>` straddles the
    :class:`Broker` thread and user threads, it is safe to call anywhere.

    **Note:** This is the somewhat limited core version of the Router class
    used by child contexts. The master subclass is documented below this one.
    """
    context_class = Context
    max_message_size = 128 * 1048576

    #: When :data:`True`, permit children to only communicate with the current
    #: context or a parent of the current context. Routing between siblings or
    #: children of parents is prohibited, ensuring no communication is possible
    #: between intentionally partitioned networks, such as when a program
    #: simultaneously manipulates hosts spread across a corporate and a
    #: production network, or production networks that are otherwise
    #: air-gapped.
    #:
    #: Sending a prohibited message causes an error to be logged and a dead
    #: message to be sent in reply to the errant message, if that message has
    #: ``reply_to`` set.
    #:
    #: The value of :data:`unidirectional` becomes the default for the
    #: :meth:`local() <mitogen.master.Router.local>` `unidirectional`
    #: parameter.
    unidirectional = False

    def __init__(self, broker):
        self.broker = broker
        listen(broker, 'exit', self._on_broker_exit)
        self._setup_logging()

        self._write_lock = threading.Lock()
        #: context ID -> Stream; must hold _write_lock to edit or iterate
        self._stream_by_id = {}
        #: List of contexts to notify of shutdown; must hold _write_lock
        self._context_by_id = {}
        self._last_handle = itertools.count(1000)
        #: handle -> (persistent?, func(msg))
        self._handle_map = {}
        #: Context -> set { handle, .. }
        self._handles_by_respondent = {}
        self.add_handler(self._on_del_route, DEL_ROUTE)

    def __repr__(self):
        return 'Router(%r)' % (self.broker,)

    def _setup_logging(self):
        """
        This is done in the :class:`Router` constructor for historical reasons.
        It must be called before ExternalContext logs its first messages, but
        after logging has been setup. It must also be called when any router is
        constructed for a consumer app.
        """
        # Here seems as good a place as any.
        global _v, _vv
        _v = logging.getLogger().level <= logging.DEBUG
        _vv = IOLOG.level <= logging.DEBUG

    def _on_del_route(self, msg):
        """
        Stub :data:`DEL_ROUTE` handler; fires 'disconnect' events on the
        corresponding :attr:`_context_by_id` member. This is replaced by
        :class:`mitogen.parent.RouteMonitor` in an upgraded context.
        """
        LOG.error('%r._on_del_route() %r', self, msg)
        if msg.is_dead:
            return

        target_id_s, _, name = bytes_partition(msg.data, b(':'))
        target_id = int(target_id_s, 10)
        context = self._context_by_id.get(target_id)
        if context:
            fire(context, 'disconnect')
        else:
            LOG.debug('DEL_ROUTE for unknown ID %r: %r', target_id, msg)

    def _on_stream_disconnect(self, stream):
        notify = []
        self._write_lock.acquire()
        try:
            for context in list(self._context_by_id.values()):
                stream_ = self._stream_by_id.get(context.context_id)
                if stream_ is stream:
                    del self._stream_by_id[context.context_id]
                    notify.append(context)
        finally:
            self._write_lock.release()

        # Happens outside lock as e.g. RouteMonitor wants the same lock.
        for context in notify:
            context.on_disconnect()

    broker_exit_msg = 'Broker has exitted'

    def _on_broker_exit(self):
        while self._handle_map:
            _, (_, func, _, _) = self._handle_map.popitem()
            func(Message.dead(self.broker_exit_msg))

    def myself(self):
        """
        Return a :class:`Context` referring to the current process.
        """
        return self.context_class(
            router=self,
            context_id=mitogen.context_id,
            name='self',
        )

    def context_by_id(self, context_id, via_id=None, create=True, name=None):
        """
        Messy factory/lookup function to find a context by its ID, or construct
        it. This will eventually be replaced by a more sensible interface.
        """
        context = self._context_by_id.get(context_id)
        if context:
            return context

        if create and via_id is not None:
            via = self.context_by_id(via_id)
        else:
            via = None

        self._write_lock.acquire()
        try:
            context = self._context_by_id.get(context_id)
            if create and not context:
                context = self.context_class(self, context_id, name=name)
                context.via = via
                self._context_by_id[context_id] = context
        finally:
            self._write_lock.release()

        return context

    def register(self, context, stream):
        """
        Register a newly constructed context and its associated stream, and add
        the stream's receive side to the I/O multiplexer. This method remains
        public while the design has not yet settled.
        """
        _v and LOG.debug('register(%r, %r)', context, stream)
        self._write_lock.acquire()
        try:
            self._stream_by_id[context.context_id] = stream
            self._context_by_id[context.context_id] = context
        finally:
            self._write_lock.release()

        self.broker.start_receive(stream)
        listen(stream, 'disconnect', lambda: self._on_stream_disconnect(stream))

    def stream_by_id(self, dst_id):
        """
        Return the :class:`Stream` that should be used to communicate with
        `dst_id`. If a specific route for `dst_id` is not known, a reference to
        the parent context's stream is returned.
        """
        return (
            self._stream_by_id.get(dst_id) or
            self._stream_by_id.get(mitogen.parent_id)
        )

    def del_handler(self, handle):
        """
        Remove the handle registered for `handle`

        :raises KeyError:
            The handle wasn't registered.
        """
        _, _, _, respondent = self._handle_map.pop(handle)
        if respondent:
            self._handles_by_respondent[respondent].discard(handle)

    def add_handler(self, fn, handle=None, persist=True,
                    policy=None, respondent=None,
                    overwrite=False):
        """
        Invoke `fn(msg)` on the :class:`Broker` thread for each Message sent to
        `handle` from this context. Unregister after one invocation if
        `persist` is :data:`False`. If `handle` is :data:`None`, a new handle
        is allocated and returned.

        :param int handle:
            If not :data:`None`, an explicit handle to register, usually one of
            the ``mitogen.core.*`` constants. If unspecified, a new unused
            handle will be allocated.

        :param bool persist:
            If :data:`False`, the handler will be unregistered after a single
            message has been received.

        :param Context respondent:
            Context that messages to this handle are expected to be sent from.
            If specified, arranges for a dead message to be delivered to `fn`
            when disconnection of the context is detected.

            In future `respondent` will likely also be used to prevent other
            contexts from sending messages to the handle.

        :param function policy:
            Function invoked as `policy(msg, stream)` where `msg` is a
            :class:`mitogen.core.Message` about to be delivered, and `stream`
            is the :class:`mitogen.core.Stream` on which it was received. The
            function must return :data:`True`, otherwise an error is logged and
            delivery is refused.

            Two built-in policy functions exist:

            * :func:`has_parent_authority`: requires the message arrived from a
              parent context, or a context acting with a parent context's
              authority (``auth_id``).

            * :func:`mitogen.parent.is_immediate_child`: requires the
              message arrived from an immediately connected child, for use in
              messaging patterns where either something becomes buggy or
              insecure by permitting indirect upstream communication.

            In case of refusal, and the message's ``reply_to`` field is
            nonzero, a :class:`mitogen.core.CallError` is delivered to the
            sender indicating refusal occurred.

        :param bool overwrite:
            If :data:`True`, allow existing handles to be silently overwritten.

        :return:
            `handle`, or if `handle` was :data:`None`, the newly allocated
            handle.
        :raises Error:
            Attemp to register handle that was already registered.
        """
        handle = handle or next(self._last_handle)
        _vv and IOLOG.debug('%r.add_handler(%r, %r, %r)', self, fn, handle, persist)
        if handle in self._handle_map and not overwrite:
            raise Error(self.duplicate_handle_msg)

        self._handle_map[handle] = persist, fn, policy, respondent
        if respondent:
            if respondent not in self._handles_by_respondent:
                self._handles_by_respondent[respondent] = set()
                listen(respondent, 'disconnect',
                       lambda: self._on_respondent_disconnect(respondent))
            self._handles_by_respondent[respondent].add(handle)

        return handle

    duplicate_handle_msg = 'cannot register a handle that is already exists'
    refused_msg = 'refused by policy'
    invalid_handle_msg = 'invalid handle'
    too_large_msg = 'message too large (max %d bytes)'
    respondent_disconnect_msg = 'the respondent Context has disconnected'
    broker_shutdown_msg = 'Broker is shutting down'
    no_route_msg = 'no route to %r, my ID is %r'
    unidirectional_msg = (
        'routing mode prevents forward of message from context %d via '
        'context %d'
    )

    def _on_respondent_disconnect(self, context):
        for handle in self._handles_by_respondent.pop(context, ()):
            _, fn, _, _  = self._handle_map[handle]
            fn(Message.dead(self.respondent_disconnect_msg))
            del self._handle_map[handle]

    def on_shutdown(self, broker):
        """Called during :meth:`Broker.shutdown`, informs callbacks registered
        with :meth:`add_handle_cb` the connection is dead."""
        _v and LOG.debug('%r.on_shutdown(%r)', self, broker)
        fire(self, 'shutdown')
        for handle, (persist, fn) in self._handle_map.iteritems():
            _v and LOG.debug('%r.on_shutdown(): killing %r: %r', self, handle, fn)
            fn(Message.dead(self.broker_shutdown_msg))

    def _maybe_send_dead(self, msg, reason, *args):
        if args:
            reason %= args
        LOG.debug('%r: %r is dead: %r', self, msg, reason)
        if msg.reply_to and not msg.is_dead:
            msg.reply(Message.dead(reason=reason), router=self)

    def _invoke(self, msg, stream):
        # IOLOG.debug('%r._invoke(%r)', self, msg)
        try:
            persist, fn, policy, respondent = self._handle_map[msg.handle]
        except KeyError:
            self._maybe_send_dead(msg, reason=self.invalid_handle_msg)
            return

        if respondent and not (msg.is_dead or
                               msg.src_id == respondent.context_id):
            self._maybe_send_dead(msg, 'reply from unexpected context')
            return

        if policy and not policy(msg, stream):
            self._maybe_send_dead(msg, self.refused_msg)
            return

        if not persist:
            self.del_handler(msg.handle)

        try:
            fn(msg)
        except Exception:
            LOG.exception('%r._invoke(%r): %r crashed', self, msg, fn)

    def _async_route(self, msg, in_stream=None):
        """
        Arrange for `msg` to be forwarded towards its destination. If its
        destination is the local context, then arrange for it to be dispatched
        using the local handlers.

        This is a lower overhead version of :meth:`route` that may only be
        called from the :class:`Broker` thread.

        :param Stream in_stream:
            If not :data:`None`, the stream the message arrived on. Used for
            performing source route verification, to ensure sensitive messages
            such as ``CALL_FUNCTION`` arrive only from trusted contexts.
        """
        _vv and IOLOG.debug('%r._async_route(%r, %r)', self, msg, in_stream)

        if len(msg.data) > self.max_message_size:
            self._maybe_send_dead(msg, self.too_large_msg % (
                self.max_message_size,
            ))
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

            # Maintain a set of IDs the source ever communicated with.
            in_stream.egress_ids.add(msg.dst_id)

        if msg.dst_id == mitogen.context_id:
            return self._invoke(msg, in_stream)

        out_stream = self._stream_by_id.get(msg.dst_id)
        if out_stream is None:
            out_stream = self._stream_by_id.get(mitogen.parent_id)

        if out_stream is None:
            self._maybe_send_dead(msg, self.no_route_msg,
                                  msg.dst_id, mitogen.context_id)
            return

        if in_stream and self.unidirectional and not \
                (in_stream.is_privileged or out_stream.is_privileged):
            self._maybe_send_dead(msg, self.unidirectional_msg,
                in_stream.remote_id, out_stream.remote_id)
            return

        out_stream._send(msg)

    def route(self, msg):
        """
        Arrange for the :class:`Message` `msg` to be delivered to its
        destination using any relevant downstream context, or if none is found,
        by forwarding the message upstream towards the master context. If `msg`
        is destined for the local context, it is dispatched using the handles
        registered with :meth:`add_handler`.

        This may be called from any thread.
        """
        self.broker.defer(self._async_route, msg)


class Broker(object):
    """
    Responsible for handling I/O multiplexing in a private thread.

    **Note:** This is the somewhat limited core version of the Broker class
    used by child contexts. The master subclass is documented below.
    """
    poller_class = Poller
    _waker = None
    _thread = None

    #: Seconds grace to allow :class:`streams <Stream>` to shutdown gracefully
    #: before force-disconnecting them during :meth:`shutdown`.
    shutdown_timeout = 3.0

    def __init__(self, poller_class=None):
        self._alive = True
        self._exitted = False
        self._waker = Waker(self)
        #: Arrange for `func(\*args, \**kwargs)` to be executed on the broker
        #: thread, or immediately if the current thread is the broker thread.
        #: Safe to call from any thread.
        self.defer = self._waker.defer
        self.poller = self.poller_class()
        self.poller.start_receive(
            self._waker.receive_side.fd,
            (self._waker.receive_side, self._waker.on_receive)
        )
        self._thread = threading.Thread(
            target=self._broker_main,
            name='mitogen.broker'
        )
        self._thread.start()

    def start_receive(self, stream):
        """
        Mark the :attr:`receive_side <Stream.receive_side>` on `stream` as
        ready for reading. Safe to call from any thread. When the associated
        file descriptor becomes ready for reading,
        :meth:`BasicStream.on_receive` will be called.
        """
        _vv and IOLOG.debug('%r.start_receive(%r)', self, stream)
        side = stream.receive_side
        assert side and side.fd is not None
        self.defer(self.poller.start_receive,
                   side.fd, (side, stream.on_receive))

    def stop_receive(self, stream):
        """
        Mark the :attr:`receive_side <Stream.receive_side>` on `stream` as not
        ready for reading. Safe to call from any thread.
        """
        _vv and IOLOG.debug('%r.stop_receive(%r)', self, stream)
        self.defer(self.poller.stop_receive, stream.receive_side.fd)

    def _start_transmit(self, stream):
        """
        Mark the :attr:`transmit_side <Stream.transmit_side>` on `stream` as
        ready for writing. Must only be called from the Broker thread. When the
        associated file descriptor becomes ready for writing,
        :meth:`BasicStream.on_transmit` will be called.
        """
        _vv and IOLOG.debug('%r._start_transmit(%r)', self, stream)
        side = stream.transmit_side
        assert side and side.fd is not None
        self.poller.start_transmit(side.fd, (side, stream.on_transmit))

    def _stop_transmit(self, stream):
        """
        Mark the :attr:`transmit_side <Stream.receive_side>` on `stream` as not
        ready for writing.
        """
        _vv and IOLOG.debug('%r._stop_transmit(%r)', self, stream)
        self.poller.stop_transmit(stream.transmit_side.fd)

    def keep_alive(self):
        """
        Return :data:`True` if any reader's :attr:`Side.keep_alive` attribute
        is :data:`True`, or any :class:`Context` is still registered that is
        not the master. Used to delay shutdown while some important work is in
        progress (e.g. log draining).
        """
        it = (side.keep_alive for (_, (side, _)) in self.poller.readers)
        return sum(it, 0)

    def defer_sync(self, func):
        """
        Arrange for `func()` to execute on :class:`Broker` thread, blocking the
        current thread until a result or exception is available.

        :returns:
            Return value of `func()`.
        """
        latch = Latch()
        def wrapper():
            try:
                latch.put(func())
            except Exception:
                latch.put(sys.exc_info()[1])
        self.defer(wrapper)
        res = latch.get()
        if isinstance(res, Exception):
            raise res
        return res

    def _call(self, stream, func):
        """
        Call `func(self)`, catching any exception that might occur, logging it,
        and force-disconnecting the related `stream`.
        """
        try:
            func(self)
        except Exception:
            LOG.exception('%r crashed', stream)
            stream.on_disconnect(self)

    def _loop_once(self, timeout=None):
        """
        Execute a single :class:`Poller` wait, dispatching any IO events that
        caused the wait to complete.

        :param float timeout:
            If not :data:`None`, maximum time in seconds to wait for events.
        """
        _vv and IOLOG.debug('%r._loop_once(%r, %r)',
                            self, timeout, self.poller)
        #IOLOG.debug('readers =\n%s', pformat(self.poller.readers))
        #IOLOG.debug('writers =\n%s', pformat(self.poller.writers))
        for side, func in self.poller.poll(timeout):
            self._call(side.stream, func)

    def _broker_exit(self):
        """
        Forcefully call :meth:`Stream.on_disconnect` on any streams that failed
        to shut down gracefully, then discard the :class:`Poller`.
        """
        for _, (side, _) in self.poller.readers + self.poller.writers:
            LOG.debug('_broker_main() force disconnecting %r', side)
            side.stream.on_disconnect(self)

        self.poller.close()

    def _broker_shutdown(self):
        """
        Invoke :meth:`Stream.on_shutdown` for every active stream, then allow
        up to :attr:`shutdown_timeout` seconds for the streams to unregister
        themselves, logging an error if any did not unregister during the grace
        period.
        """
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

    def _do_broker_main(self):
        """
        Broker thread main function. Dispatches IO events until
        :meth:`shutdown` is called.
        """
        # For Python 2.4, no way to retrieve ident except on thread.
        self._waker.broker_ident = thread.get_ident()
        try:
            while self._alive:
                self._loop_once()

            fire(self, 'shutdown')
            self._broker_shutdown()
        except Exception:
            LOG.exception('_broker_main() crashed')

        self._exitted = True
        self._broker_exit()

    def _broker_main(self):
        _profile_hook('mitogen.broker', self._do_broker_main)
        fire(self, 'exit')

    def shutdown(self):
        """
        Request broker gracefully disconnect streams and stop. Safe to call
        from any thread.
        """
        _v and LOG.debug('%r.shutdown()', self)
        def _shutdown():
            self._alive = False
        if self._alive and not self._exitted:
            self.defer(_shutdown)

    def join(self):
        """
        Wait for the broker to stop, expected to be called after
        :meth:`shutdown`.
        """
        self._thread.join()

    def __repr__(self):
        return 'Broker(%#x)' % (id(self),)


class Dispatcher(object):
    """
    Implementation of the :data:`CALL_FUNCTION` handle for a child context.
    Listens on the child's main thread for messages sent by
    :class:`mitogen.parent.CallChain` and dispatches the function calls they
    describe.

    If a :class:`mitogen.parent.CallChain` sending a message is in pipelined
    mode, any exception that occurs is recorded, and causes all subsequent
    calls with the same `chain_id` to fail with the same exception.
    """
    def __init__(self, econtext):
        self.econtext = econtext
        #: Chain ID -> CallError if prior call failed.
        self._error_by_chain_id = {}
        self.recv = Receiver(router=econtext.router,
                             handle=CALL_FUNCTION,
                             policy=has_parent_authority)
        listen(econtext.broker, 'shutdown', self.recv.close)

    @classmethod
    @takes_econtext
    def forget_chain(cls, chain_id, econtext):
        econtext.dispatcher._error_by_chain_id.pop(chain_id, None)

    def _parse_request(self, msg):
        data = msg.unpickle(throw=False)
        _v and LOG.debug('_dispatch_one(%r)', data)

        chain_id, modname, klass, func, args, kwargs = data
        obj = import_module(modname)
        if klass:
            obj = getattr(obj, klass)
        fn = getattr(obj, func)
        if getattr(fn, 'mitogen_takes_econtext', None):
            kwargs.setdefault('econtext', self.econtext)
        if getattr(fn, 'mitogen_takes_router', None):
            kwargs.setdefault('router', self.econtext.router)

        return chain_id, fn, args, kwargs

    def _dispatch_one(self, msg):
        try:
            chain_id, fn, args, kwargs = self._parse_request(msg)
        except Exception:
            return None, CallError(sys.exc_info()[1])

        if chain_id in self._error_by_chain_id:
            return chain_id, self._error_by_chain_id[chain_id]

        try:
            return chain_id, fn(*args, **kwargs)
        except Exception:
            e = CallError(sys.exc_info()[1])
            if chain_id is not None:
                self._error_by_chain_id[chain_id] = e
            return chain_id, e

    def _dispatch_calls(self):
        for msg in self.recv:
            chain_id, ret = self._dispatch_one(msg)
            _v and LOG.debug('_dispatch_calls: %r -> %r', msg, ret)
            if msg.reply_to:
                msg.reply(ret)
            elif isinstance(ret, CallError) and chain_id is None:
                LOG.error('No-reply function call failed: %s', ret)

    def run(self):
        if self.econtext.config.get('on_start'):
            self.econtext.config['on_start'](self.econtext)

        _profile_hook('mitogen.child_main', self._dispatch_calls)


class ExternalContext(object):
    """
    External context implementation.

    .. attribute:: broker
        The :class:`mitogen.core.Broker` instance.

    .. attribute:: context
        The :class:`mitogen.core.Context` instance.

    .. attribute:: channel
        The :class:`mitogen.core.Channel` over which :data:`CALL_FUNCTION`
        requests are received.

    .. attribute:: stdout_log
        The :class:`mitogen.core.IoLogger` connected to ``stdout``.

    .. attribute:: importer
        The :class:`mitogen.core.Importer` instance.

    .. attribute:: stdout_log
        The :class:`IoLogger` connected to ``stdout``.

    .. attribute:: stderr_log
        The :class:`IoLogger` connected to ``stderr``.

    .. method:: _dispatch_calls
        Implementation for the main thread in every child context.
    """
    detached = False

    def __init__(self, config):
        self.config = config

    def _on_broker_exit(self):
        if not self.config['profiling']:
            os.kill(os.getpid(), signal.SIGTERM)

    #: On Python >3.4, the global importer lock has been sharded into a
    #: per-module lock, meaning there is no guarantee the import statement in
    #: service_stub_main will be truly complete before a second thread
    #: attempting the same import will see a partially initialized module.
    #: Sigh. Therefore serialize execution of the stub itself.
    service_stub_lock = threading.Lock()

    def _service_stub_main(self, msg):
        self.service_stub_lock.acquire()
        try:
            import mitogen.service
            pool = mitogen.service.get_or_create_pool(router=self.router)
            pool._receiver._on_receive(msg)
        finally:
            self.service_stub_lock.release()

    def _on_call_service_msg(self, msg):
        """
        Stub service handler. Start a thread to import the mitogen.service
        implementation from, and deliver the message to the newly constructed
        pool. This must be done as CALL_SERVICE for e.g. PushFileService may
        race with a CALL_FUNCTION blocking the main thread waiting for a result
        from that service.
        """
        if not msg.is_dead:
            th = threading.Thread(target=self._service_stub_main, args=(msg,))
            th.start()

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

    def detach(self):
        self.detached = True
        stream = self.router.stream_by_id(mitogen.parent_id)
        if stream:  # not double-detach()'d
            os.setsid()
            self.parent.send_await(Message(handle=DETACHING))
            LOG.info('Detaching from %r; parent is %s', stream, self.parent)
            for x in range(20):
                pending = self.broker.defer_sync(lambda: stream.pending_bytes())
                if not pending:
                    break
                time.sleep(0.05)
            if pending:
                LOG.error('Stream had %d bytes after 2000ms', pending)
            self.broker.defer(stream.on_disconnect, self.broker)

    def _setup_master(self):
        Router.max_message_size = self.config['max_message_size']
        if self.config['profiling']:
            enable_profiling()
        self.broker = Broker()
        self.router = Router(self.broker)
        self.router.debug = self.config.get('debug', False)
        self.router.undirectional = self.config['unidirectional']
        self.router.add_handler(
            fn=self._on_shutdown_msg,
            handle=SHUTDOWN,
            policy=has_parent_authority,
        )
        self.router.add_handler(
            fn=self._on_call_service_msg,
            handle=CALL_SERVICE,
            policy=has_parent_authority,
        )
        self.master = Context(self.router, 0, 'master')
        parent_id = self.config['parent_ids'][0]
        if parent_id == 0:
            self.parent = self.master
        else:
            self.parent = Context(self.router, parent_id, 'parent')

        in_fd = self.config.get('in_fd', 100)
        out_fd = self.config.get('out_fd', 1)
        self.stream = Stream(self.router, parent_id)
        self.stream.name = 'parent'
        self.stream.accept(in_fd, out_fd)
        self.stream.receive_side.keep_alive = False

        listen(self.stream, 'disconnect', self._on_parent_disconnect)
        listen(self.broker, 'exit', self._on_broker_exit)

        os.close(in_fd)

    def _reap_first_stage(self):
        try:
            os.wait()  # Reap first stage.
        except OSError:
            pass  # No first stage exists (e.g. fakessh)

    def _setup_logging(self):
        self.log_handler = LogHandler(self.master)
        root = logging.getLogger()
        root.setLevel(self.config['log_level'])
        root.handlers = [self.log_handler]
        if self.config['debug']:
            enable_debug_logging()

    def _setup_importer(self):
        importer = self.config.get('importer')
        if importer:
            importer._install_handler(self.router)
            importer._context = self.parent
        else:
            core_src_fd = self.config.get('core_src_fd', 101)
            if core_src_fd:
                fp = os.fdopen(core_src_fd, 'rb', 1)
                try:
                    core_src = fp.read()
                    # Strip "ExternalContext.main()" call from last line.
                    core_src = b('\n').join(core_src.splitlines()[:-1])
                finally:
                    fp.close()
            else:
                core_src = None

            importer = Importer(
                self.router,
                self.parent,
                core_src,
                self.config.get('whitelist', ()),
                self.config.get('blacklist', ()),
            )

        self.importer = importer
        self.router.importer = importer
        sys.meta_path.insert(0, self.importer)

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

    def _setup_globals(self):
        mitogen.is_master = False
        mitogen.__version__ = self.config['version']
        mitogen.context_id = self.config['context_id']
        mitogen.parent_ids = self.config['parent_ids'][:]
        mitogen.parent_id = mitogen.parent_ids[0]

    def _nullify_stdio(self):
        """
        Open /dev/null to replace stdin, and stdout/stderr temporarily. In case
        of odd startup, assume we may be allocated a standard handle.
        """
        fd = os.open('/dev/null', os.O_RDWR)
        try:
            for stdfd in (0, 1, 2):
                if fd != stdfd:
                    os.dup2(fd, stdfd)
        finally:
            if fd not in (0, 1, 2):
                os.close(fd)

    def _setup_stdio(self):
        # #481: when stderr is a TTY due to being started via
        # tty_create_child()/hybrid_tty_create_child(), and some privilege
        # escalation tool like prehistoric versions of sudo exec this process
        # over the top of itself, there is nothing left to keep the slave PTY
        # open after we replace our stdio. Therefore if stderr is a TTY, keep
        # around a permanent dup() to avoid receiving SIGHUP.
        try:
            if os.isatty(2):
                self.reserve_tty_fd = os.dup(2)
                set_cloexec(self.reserve_tty_fd)
        except OSError:
            pass
        # When sys.stdout was opened by the runtime, overwriting it will not
        # close FD 1. However when forking from a child that previously used
        # fdopen(), overwriting it /will/ close FD 1. So we must swallow the
        # close before IoLogger overwrites FD 1, otherwise its new FD 1 will be
        # clobbered. Additionally, stdout must be replaced with /dev/null prior
        # to stdout.close(), since if block buffering was active in the parent,
        # any pre-fork buffered data will be flushed on close(), corrupting the
        # connection to the parent.
        self._nullify_stdio()
        sys.stdout.close()
        self._nullify_stdio()

        self.stdout_log = IoLogger(self.broker, 'stdout', 1)
        self.stderr_log = IoLogger(self.broker, 'stderr', 2)
        # Reopen with line buffering.
        sys.stdout = os.fdopen(1, 'w', 1)

    def main(self):
        self._setup_master()
        try:
            try:
                self._setup_logging()
                self._setup_importer()
                self._reap_first_stage()
                if self.config.get('setup_package', True):
                    self._setup_package()
                self._setup_globals()
                if self.config.get('setup_stdio', True):
                    self._setup_stdio()

                self.dispatcher = Dispatcher(self)
                self.router.register(self.parent, self.stream)
                self.router._setup_logging()
                self.log_handler.uncork()

                sys.executable = os.environ.pop('ARGV0', sys.executable)
                _v and LOG.debug('Connected to context %s; my ID is %r',
                                 self.parent, mitogen.context_id)
                _v and LOG.debug('pid:%r ppid:%r uid:%r/%r, gid:%r/%r host:%r',
                                 os.getpid(), os.getppid(), os.geteuid(),
                                 os.getuid(), os.getegid(), os.getgid(),
                                 socket.gethostname())
                _v and LOG.debug('Recovered sys.executable: %r', sys.executable)

                self.dispatcher.run()
                _v and LOG.debug('ExternalContext.main() normal exit')
            except KeyboardInterrupt:
                LOG.debug('KeyboardInterrupt received, exiting gracefully.')
            except BaseException:
                LOG.exception('ExternalContext.main() crashed')
                raise
        finally:
            self.broker.shutdown()
            self.broker.join()
