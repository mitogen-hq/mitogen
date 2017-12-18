# Copyright 2017, David Wilson
#
# Redistribution and use in source and binary forms, with or without
# modification, are permitted provided that the following conditions are met:
#
# 1. Redistributions of source code must retain the above copyright notice, this
# list of conditions and the following disclaimer.
#
# 2. Redistributions in binary form must reproduce the above copyright notice,
# this list of conditions and the following disclaimer in the documentation
# and/or other materials provided with the distribution.
#
# 3. Neither the name of the copyright holder nor the names of its contributors
# may be used to endorse or promote products derived from this software without
# specific prior written permission.
#
# THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS" AND
# ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE IMPLIED
# WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE
# DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT HOLDER OR CONTRIBUTORS BE LIABLE
# FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL
# DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR
# SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER
# CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY,
# OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE
# OF THIS SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.

import dis
import errno
import getpass
import imp
import inspect
import itertools
import logging
import os
import pkgutil
import pty
import re
import select
import signal
import socket
import sys
import termios
import textwrap
import threading
import time
import types
import zlib

try:
    import Queue
except ImportError:
    import queue as Queue

if not hasattr(pkgutil, 'find_loader'):
    # find_loader() was new in >=2.5, but the modern pkgutil.py syntax has
    # been kept intentionally 2.3 compatible so we can reuse it.
    from mitogen.compat import pkgutil

import mitogen.core


LOG = logging.getLogger('mitogen')
IOLOG = logging.getLogger('mitogen.io')
RLOG = logging.getLogger('mitogen.ctx')

DOCSTRING_RE = re.compile(r'""".+?"""', re.M | re.S)
COMMENT_RE = re.compile(r'^[ ]*#[^\n]*$', re.M)
IOLOG_RE = re.compile(r'^[ ]*IOLOG.debug\(.+?\)$', re.M)


def minimize_source(source):
    subber = lambda match: '""' + ('\n' * match.group(0).count('\n'))
    source = DOCSTRING_RE.sub(subber, source)
    source = COMMENT_RE.sub('', source)
    return source.replace('    ', '\t')


def get_child_modules(path, fullname):
    it = pkgutil.iter_modules([os.path.dirname(path)])
    return ['%s.%s' % (fullname, name) for _, name, _ in it]


class Argv(object):
    def __init__(self, argv):
        self.argv = argv

    def escape(self, x):
        s = '"'
        for c in x:
            if c in '\\$"`':
                s += '\\'
            s += c
        s += '"'
        return s

    def __str__(self):
        return ' '.join(map(self.escape, self.argv))


def create_child(*args):
    parentfp, childfp = socket.socketpair()
    pid = os.fork()
    if not pid:
        mitogen.core.set_block(childfp.fileno())
        os.dup2(childfp.fileno(), 0)
        os.dup2(childfp.fileno(), 1)
        childfp.close()
        parentfp.close()
        os.execvp(args[0], args)

    childfp.close()
    # Decouple the socket from the lifetime of the Python socket object.
    fd = os.dup(parentfp.fileno())
    parentfp.close()

    LOG.debug('create_child() child %d fd %d, parent %d, cmd: %s',
              pid, fd, os.getpid(), Argv(args))
    return pid, fd


def flags(names):
    """Return the result of ORing a set of (space separated) :py:mod:`termios`
    module constants together."""
    return sum(getattr(termios, name) for name in names.split())


def cfmakeraw(tflags):
    """Given a list returned by :py:func:`termios.tcgetattr`, return a list
    that has been modified in the same manner as the `cfmakeraw()` C library
    function."""
    iflag, oflag, cflag, lflag, ispeed, ospeed, cc = tflags
    iflag &= ~flags('IGNBRK BRKINT PARMRK ISTRIP INLCR IGNCR ICRNL IXON')
    oflag &= ~flags('OPOST IXOFF')
    lflag &= ~flags('ECHO ECHOE ECHONL ICANON ISIG IEXTEN')
    cflag &= ~flags('CSIZE PARENB')
    cflag |= flags('CS8')

    # TODO: one or more of the above bit twiddles sets or omits a necessary
    # flag. Forcing these fields to zero, as shown below, gets us what we want
    # on Linux/OS X, but it is possibly broken on some other OS.
    iflag = 0
    oflag = 0
    lflag = 0
    return [iflag, oflag, cflag, lflag, ispeed, ospeed, cc]


def disable_echo(fd):
    old = termios.tcgetattr(fd)
    new = cfmakeraw(old)
    flags = (
        termios.TCSAFLUSH |
        getattr(termios, 'TCSASOFT', 0)
    )
    termios.tcsetattr(fd, flags, new)


def close_nonstandard_fds():
    for fd in xrange(3, 1024):
        try:
            os.close(fd)
        except OSError:
            pass


def tty_create_child(*args):
    master_fd, slave_fd = os.openpty()
    disable_echo(master_fd)
    disable_echo(slave_fd)

    pid = os.fork()
    if not pid:
        os.dup2(slave_fd, 0)
        os.dup2(slave_fd, 1)
        os.dup2(slave_fd, 2)
        close_nonstandard_fds()
        os.setsid()
        os.close(os.open(os.ttyname(1), os.O_RDWR))
        os.execvp(args[0], args)

    os.close(slave_fd)
    LOG.debug('tty_create_child() child %d fd %d, parent %d, cmd: %s',
              pid, master_fd, os.getpid(), Argv(args))
    return pid, master_fd


def write_all(fd, s, deadline=None):
    timeout = None
    written = 0

    while written < len(s):
        if deadline is not None:
            timeout = max(0, deadline - time.time())
        if timeout == 0:
            raise mitogen.core.TimeoutError('write timed out')

        _, wfds, _ = select.select([], [fd], [], timeout)
        if not wfds:
            continue

        n, disconnected = mitogen.core.io_op(os.write, fd, buffer(s, written))
        if disconnected:
            raise mitogen.core.StreamError('EOF on stream during write')

        written += n


def iter_read(fd, deadline=None):
    bits = []
    timeout = None

    while True:
        if deadline is not None:
            timeout = max(0, deadline - time.time())
            if timeout == 0:
                break

        rfds, _, _ = select.select([fd], [], [], timeout)
        if not rfds:
            continue

        s, disconnected = mitogen.core.io_op(os.read, fd, 4096)
        IOLOG.debug('iter_read(%r) -> %r', fd, s)
        if disconnected or not s:
            raise mitogen.core.StreamError(
                'EOF on stream; last 300 bytes received: %r' %
                (''.join(bits)[-300:],)
            )

        bits.append(s)
        yield s

    raise mitogen.core.TimeoutError('read timed out')


def discard_until(fd, s, deadline):
    for buf in iter_read(fd, deadline):
        if buf.endswith(s):
            return


def scan_code_imports(co, LOAD_CONST=dis.opname.index('LOAD_CONST'),
                          IMPORT_NAME=dis.opname.index('IMPORT_NAME')):
    """Given a code object `co`, scan its bytecode yielding any
    ``IMPORT_NAME`` and associated prior ``LOAD_CONST`` instructions
    representing an `Import` statement or `ImportFrom` statement.

    :return:
        Generator producing `(level, modname, namelist)` tuples, where:

        * `level`: -1 for normal import, 0, for absolute import, and >0 for
          relative import.
        * `modname`: Name of module to import, or from where `namelist` names
          are imported.
        * `namelist`: for `ImportFrom`, the list of names to be imported from
          `modname`.
    """
    # Yield `(op, oparg)` tuples from the code object `co`.
    ordit = itertools.imap(ord, co.co_code)
    nextb = ordit.next

    opit = ((c, (None
                 if c < dis.HAVE_ARGUMENT else
                 (nextb() | (nextb() << 8))))
            for c in ordit)

    opit, opit2, opit3 = itertools.tee(opit, 3)
    next(opit2)
    next(opit3)
    next(opit3)

    for oparg1, oparg2, (op3, arg3) in itertools.izip(opit, opit2, opit3):
        if op3 == IMPORT_NAME:
            op2, arg2 = oparg2
            op1, arg1 = oparg1
            if op1 == op2 == LOAD_CONST:
                yield (co.co_consts[arg1],
                       co.co_names[arg3],
                       co.co_consts[arg2] or ())


def join_thread_async(target_thread, on_join):
    """Start a thread that waits for another thread to shutdown, before
    invoking `on_join()`. In CPython it seems possible to use this method to
    ensure a non-main thread is signalled when the main thread has exitted,
    using yet another thread as a proxy."""
    def _watch():
        target_thread.join()
        on_join()
    thread = threading.Thread(target=_watch)
    thread.start()


class SelectError(mitogen.core.Error):
    pass


class Select(object):
    notify = None

    def __init__(self, receivers=(), oneshot=True):
        self._receivers = []
        self._oneshot = oneshot
        self._queue = Queue.Queue()
        for recv in receivers:
            self.add(recv)

    def _put(self, value):
        self._queue.put(value)
        if self.notify:
            self.notify(self)

    def __bool__(self):
        return bool(self._receivers)

    def __enter__(self):
        return self

    def __exit__(self, e_type, e_val, e_tb):
        self.close()

    def __iter__(self):
        while self._receivers:
            recv, msg = self.get()
            yield recv, msg

    loop_msg = 'Adding this Select instance would create a Select cycle'

    def _check_no_loop(self, recv):
        if recv is self:
            raise SelectError(self.loop_msg)

        for recv_ in self._receivers:
            if recv_ == recv:
                raise SelectError(self.loop_msg)
            if isinstance(recv_, Select):
                recv_._check_no_loop(recv)

    owned_msg = 'Cannot add: Receiver is already owned by another Select'

    def add(self, recv):
        if isinstance(recv, Select):
            recv._check_no_loop(self)

        self._receivers.append(recv)
        if recv.notify is not None:
            raise SelectError(self.owned_msg)

        recv.notify = self._put
        # Avoid race by polling once after installation.
        if not recv.empty():
            self._put(recv)

    not_present_msg = 'Instance is not a member of this Select'

    def remove(self, recv):
        try:
            if recv.notify != self._put:
                raise ValueError
            self._receivers.remove(recv)
            recv.notify = None
        except (IndexError, ValueError):
            raise SelectError(self.not_present_msg)

    def close(self):
        for recv in self._receivers[:]:
            self.remove(recv)

    def empty(self):
        return self._queue.empty()

    empty_msg = 'Cannot get(), Select instance is empty'

    def get(self, timeout=None):
        if not self._receivers:
            raise SelectError(self.empty_msg)

        while True:
            recv = mitogen.core._queue_interruptible_get(self._queue, timeout)
            try:
                msg = recv.get(block=False)
                if self._oneshot:
                    self.remove(recv)
                return recv, msg
            except mitogen.core.TimeoutError:
                # A receiver may have been queued with no result if another
                # thread drained it before we woke up, or because another
                # thread drained it between add() calling recv.empty() and
                # self._put(). In this case just sleep again.
                continue


class LogForwarder(object):
    def __init__(self, router):
        self._router = router
        self._cache = {}
        router.add_handler(self._on_forward_log, mitogen.core.FORWARD_LOG)

    def _on_forward_log(self, msg):
        if msg == mitogen.core._DEAD:
            return

        logger = self._cache.get(msg.src_id)
        if logger is None:
            context = self._router.context_by_id(msg.src_id)
            if context is None:
                LOG.error('FORWARD_LOG received from src_id %d', msg.src_id)
                return

            name = '%s.%s' % (RLOG.name, context.name)
            self._cache[msg.src_id] = logger = logging.getLogger(name)

        name, level_s, s = msg.data.split('\x00', 2)
        logger.log(int(level_s), '%s: %s', name, s)

    def __repr__(self):
        return 'LogForwarder(%r)' % (self._router,)


class ModuleFinder(object):
    STDLIB_DIRS = [
        # virtualenv on OS X does some weird half-ass job of symlinking the
        # stdlib into the virtualenv directory. So pick two modules at random
        # that represent both places the stdlib seems to come from.
        os.path.dirname(os.path.dirname(logging.__file__)),
        os.path.dirname(os.path.dirname(os.__file__)),
    ]

    def __init__(self):
        #: Import machinery is expensive, keep :py:meth`:get_module_source`
        #: results around.
        self._found_cache = {}

        #: Avoid repeated dependency scanning, which is expensive.
        self._related_cache = {}

    def __repr__(self):
        return 'ModuleFinder()'

    def is_stdlib_name(self, modname):
        """Return ``True`` if `modname` appears to come from the standard
        library."""
        if imp.is_builtin(modname) != 0:
            return True

        module = sys.modules.get(modname)
        if module is None:
            return False

        # six installs crap with no __file__
        modpath = getattr(module, '__file__', '')
        if 'site-packages' in modpath:
            return False

        for dirname in self.STDLIB_DIRS:
            if os.path.commonprefix((dirname, modpath)) == dirname:
                return True

        return False

    def _py_filename(self, path):
        path = path.rstrip('co')
        if path.endswith('.py'):
            return path

    def _get_module_via_pkgutil(self, fullname):
        """Attempt to fetch source code via pkgutil. In an ideal world, this
        would be the only required implementation of get_module()."""
        loader = pkgutil.find_loader(fullname)
        LOG.debug('pkgutil._get_module_via_pkgutil(%r) -> %r', fullname, loader)
        if not loader:
            return

        try:
            path = self._py_filename(loader.get_filename(fullname))
            source = loader.get_source(fullname)
            if path is not None and source is not None:
                return path, source, loader.is_package(fullname)
        except AttributeError:
            return

    def _get_module_via_sys_modules(self, fullname):
        """Attempt to fetch source code via sys.modules. This is specifically
        to support __main__, but it may catch a few more cases."""
        module = sys.modules.get(fullname)
        if not isinstance(module, types.ModuleType):
            LOG.debug('sys.modules[%r] absent or not a regular module',
                      fullname)
            return

        modpath = self._py_filename(getattr(module, '__file__', ''))
        if not modpath:
            return

        is_pkg = hasattr(module, '__path__')
        try:
            source = inspect.getsource(module)
        except IOError:
            # Work around inspect.getsourcelines() bug.
            if not is_pkg:
                raise
            source = '\n'

        return (module.__file__.rstrip('co'),
                source,
                hasattr(module, '__path__'))

    get_module_methods = [_get_module_via_pkgutil,
                          _get_module_via_sys_modules]

    def get_module_source(self, fullname):
        """Given the name of a loaded module `fullname`, attempt to find its
        source code.

        :returns:
            Tuple of `(module path, source text, is package?)`, or ``None`` if
            the source cannot be found.
        """
        tup = self._found_cache.get(fullname)
        if tup:
            return tup

        for method in self.get_module_methods:
            tup = method(self, fullname)
            if tup:
                return tup

        return None, None, None

    def resolve_relpath(self, fullname, level):
        """Given an ImportFrom AST node, guess the prefix that should be tacked
        on to an alias name to produce a canonical name. `fullname` is the name
        of the module in which the ImportFrom appears."""
        if level == 0 or not fullname:
            return ''

        bits = fullname.split('.')
        if len(bits) <= level:
            # This would be an ImportError in real code.
            return ''

        return '.'.join(bits[:-level]) + '.'

    def generate_parent_names(self, fullname):
        while '.' in fullname:
            fullname = fullname[:fullname.rindex('.')]
            yield fullname

    def find_related_imports(self, fullname):
        """
        Given the `fullname` of a currently loaded module, and a copy of its
        source code, examine :py:data:`sys.modules` to determine which of the
        ``import`` statements from the source code caused a corresponding
        module to be loaded that is not part of the standard library.
        """
        related = self._related_cache.get(fullname)
        if related is not None:
            return related

        modpath, src, _ = self.get_module_source(fullname)
        if src is None:
            LOG.warning('%r: cannot find source for %r', self, fullname)
            return []

        maybe_names = list(self.generate_parent_names(fullname))

        co = compile(src, modpath, 'exec')
        for level, modname, namelist in scan_code_imports(co):
            if level == -1:
                modnames = [modname, '%s.%s' % (fullname, modname)]
            else:
                modnames = [self.resolve_relpath(fullname, level) + modname]

            maybe_names.extend(modnames)
            maybe_names.extend(
                '%s.%s' % (mname, name)
                for mname in modnames
                for name in namelist
            )

        return self._related_cache.setdefault(fullname, sorted(
            set(
                name
                for name in maybe_names
                if sys.modules.get(name) is not None
                and not self.is_stdlib_name(name)
                and 'six.moves' not in name  # TODO: crap
            )
        ))

    def find_related(self, fullname):
        stack = [fullname]
        found = set()

        while stack:
            fullname = stack.pop(0)
            fullnames = self.find_related_imports(fullname)
            stack.extend(set(fullnames).difference(found, stack, [fullname]))
            found.update(fullnames)

        return found


class ModuleResponder(object):
    def __init__(self, router):
        self._router = router
        self._finder = ModuleFinder()
        router.add_handler(self._on_get_module, mitogen.core.GET_MODULE)

    def __repr__(self):
        return 'ModuleResponder(%r)' % (self._router,)

    MAIN_RE = re.compile(r'^if\s+__name__\s*==\s*.__main__.\s*:', re.M)

    def neutralize_main(self, src):
        """Given the source for the __main__ module, try to find where it
        begins conditional execution based on a "if __name__ == '__main__'"
        guard, and remove any code after that point."""
        match = self.MAIN_RE.search(src)
        if match:
            return src[:match.start()]
        return src

    def _on_get_module(self, msg):
        LOG.debug('%r.get_module(%r)', self, msg)
        if msg == mitogen.core._DEAD:
            return

        fullname = msg.data
        try:
            path, source, is_pkg = self._finder.get_module_source(fullname)
            if source is None:
                raise ImportError('could not find %r' % (fullname,))

            if is_pkg:
                pkg_present = get_child_modules(path, fullname)
                LOG.debug('get_child_modules(%r, %r) -> %r',
                          path, fullname, pkg_present)
            else:
                pkg_present = None

            if fullname == '__main__':
                source = self.neutralize_main(source)
            compressed = zlib.compress(source)
            related = list(self._finder.find_related(fullname))
            self._router.route(
                mitogen.core.Message.pickled(
                    (pkg_present, path, compressed, related),
                    dst_id=msg.src_id,
                    handle=msg.reply_to,
                )
            )
        except Exception:
            LOG.debug('While importing %r', fullname, exc_info=True)
            self._router.route(
                mitogen.core.Message.pickled(
                    None,
                    dst_id=msg.src_id,
                    handle=msg.reply_to,
                )
            )


class ModuleForwarder(object):
    """
    Respond to GET_MODULE requests in a slave by forwarding the request to our
    parent context, or satisfying the request from our local Importer cache.
    """
    def __init__(self, router, parent_context, importer):
        self.router = router
        self.parent_context = parent_context
        self.importer = importer
        router.add_handler(self._on_get_module, mitogen.core.GET_MODULE)

    def __repr__(self):
        return 'ModuleForwarder(%r)' % (self.router,)

    def _on_get_module(self, msg):
        LOG.debug('%r._on_get_module(%r)', self, msg)
        if msg == mitogen.core._DEAD:
            return

        fullname = msg.data
        cached = self.importer._cache.get(fullname)
        if cached:
            LOG.debug('%r._on_get_module(): using cached %r', self, fullname)
            self.router.route(
                mitogen.core.Message.pickled(
                    cached,
                    dst_id=msg.src_id,
                    handle=msg.reply_to,
                )
            )
        else:
            LOG.debug('%r._on_get_module(): requesting %r', self, fullname)
            self.parent_context.send(
                mitogen.core.Message(
                    data=msg.data,
                    handle=mitogen.core.GET_MODULE,
                    reply_to=self.router.add_handler(
                        lambda m: self._on_got_source(m, msg),
                        persist=False
                    )
                )
            )

    def _on_got_source(self, msg, original_msg):
        LOG.debug('%r._on_got_source(%r, %r)', self, msg, original_msg)
        fullname = original_msg.data
        self.importer._cache[fullname] = msg.unpickle()
        self.router.route(
            mitogen.core.Message(
                data=msg.data,
                dst_id=original_msg.src_id,
                handle=original_msg.reply_to,
            )
        )


class Stream(mitogen.core.Stream):
    """
    Base for streams capable of starting new slaves.
    """
    #: The path to the remote Python interpreter.
    python_path = 'python2.7'

    #: True to cause context to write verbose /tmp/mitogen.<pid>.log.
    debug = False

    #: True to cause context to write /tmp/mitogen.stats.<pid>.<thread>.log.
    profiling = False

    def construct(self, remote_name=None, python_path=None, debug=False,
                  profiling=False, **kwargs):
        """Get the named context running on the local machine, creating it if
        it does not exist."""
        super(Stream, self).construct(**kwargs)
        if python_path:
            self.python_path = python_path

        if remote_name is None:
            remote_name = '%s@%s:%d'
            remote_name %= (getpass.getuser(), socket.gethostname(), os.getpid())
        self.remote_name = remote_name
        self.debug = debug
        self.profiling = profiling

    def on_shutdown(self, broker):
        """Request the slave gracefully shut itself down."""
        LOG.debug('%r closing CALL_FUNCTION channel', self)
        self.send(
            mitogen.core.Message(
                src_id=mitogen.context_id,
                dst_id=self.remote_id,
                handle=mitogen.core.SHUTDOWN,
            )
        )

    # base64'd and passed to 'python -c'. It forks, dups 0->100, creates a
    # pipe, then execs a new interpreter with a custom argv. 'CONTEXT_NAME' is
    # replaced with the context name. Optimized for size.
    @staticmethod
    def _first_stage():
        import os,sys,zlib
        R,W=os.pipe()
        r,w=os.pipe()
        if os.fork():
            os.dup2(0,100)
            os.dup2(R,0)
            os.dup2(r,101)
            for f in R,r,W,w:os.close(f)
            os.environ['ARGV0']=e=sys.executable
            os.execv(e,['mitogen:CONTEXT_NAME'])
        os.write(1,'EC0\n')
        C=zlib.decompress(sys.stdin.read(input()))
        os.fdopen(W,'w',0).write(C)
        os.fdopen(w,'w',0).write('%s\n'%len(C)+C)
        os.write(1,'EC1\n')
        sys.exit(0)

    def get_boot_command(self):
        source = inspect.getsource(self._first_stage)
        source = textwrap.dedent('\n'.join(source.strip().split('\n')[2:]))
        source = source.replace('    ', '\t')
        source = source.replace('CONTEXT_NAME', self.remote_name)
        encoded = source.encode('zlib').encode('base64').replace('\n', '')
        # We can't use bytes.decode() in 3.x since it was restricted to always
        # return unicode, so codecs.decode() is used instead. In 3.x
        # codecs.decode() requires a bytes object. Since we must be compatible
        # with 2.4 (no bytes literal), an extra .encode() either returns the
        # same str (2.x) or an equivalent bytes (3.x).
        return [
            self.python_path, '-c',
            'from codecs import decode as _;'
            'exec(_(_("%s".encode(),"base64"),"zlib"))' % (encoded,)
        ]

    def get_preamble(self):
        parent_ids = mitogen.parent_ids[:]
        parent_ids.insert(0, mitogen.context_id)
        source = inspect.getsource(mitogen.core)
        source += '\nExternalContext().main%r\n' % ((
            parent_ids,                # parent_ids
            self.remote_id,            # context_id
            self.debug,
            self.profiling,
            LOG.level or logging.getLogger().level or logging.INFO,
        ),)

        compressed = zlib.compress(minimize_source(source))
        return str(len(compressed)) + '\n' + compressed

    create_child = staticmethod(create_child)

    def connect(self):
        LOG.debug('%r.connect()', self)
        pid, fd = self.create_child(*self.get_boot_command())
        self.name = 'local.%s' % (pid,)
        self.receive_side = mitogen.core.Side(self, fd)
        self.transmit_side = mitogen.core.Side(self, os.dup(fd))
        LOG.debug('%r.connect(): child process stdin/stdout=%r',
                  self, self.receive_side.fd)

        self._connect_bootstrap()

    def _ec0_received(self):
        LOG.debug('%r._ec0_received()', self)
        write_all(self.transmit_side.fd, self.get_preamble())
        discard_until(self.receive_side.fd, 'EC1\n', time.time() + 10.0)

    def _connect_bootstrap(self):
        discard_until(self.receive_side.fd, 'EC0\n', time.time() + 10.0)
        self._ec0_received()


class Broker(mitogen.core.Broker):
    shutdown_timeout = 5.0

    def __init__(self, install_watcher=True):
        if install_watcher:
            join_thread_async(threading.currentThread(), self.shutdown)
        super(Broker, self).__init__()


class Context(mitogen.core.Context):
    via = None

    def on_disconnect(self, broker):
        """
        Override base behaviour of triggering Broker shutdown on parent stream
        disconnection.
        """
        mitogen.core.fire(self, 'disconnect')

    def call_async(self, fn, *args, **kwargs):
        LOG.debug('%r.call_async(%r, *%r, **%r)',
                  self, fn, args, kwargs)

        if isinstance(fn, types.MethodType) and \
           isinstance(fn.im_self, (type, types.ClassType)):
            klass = fn.im_self.__name__
        else:
            klass = None

        recv = self.send_async(
            mitogen.core.Message.pickled(
                (fn.__module__, klass, fn.__name__, args, kwargs),
                handle=mitogen.core.CALL_FUNCTION,
            )
        )
        recv.raise_channelerror = False
        return recv

    def call(self, fn, *args, **kwargs):
        return self.call_async(fn, *args, **kwargs).get_data()


def _local_method():
    return Stream

def _ssh_method():
    import mitogen.ssh
    return mitogen.ssh.Stream

def _sudo_method():
    import mitogen.sudo
    return mitogen.sudo.Stream


METHOD_NAMES = {
    'local': _local_method,
    'ssh': _ssh_method,
    'sudo': _sudo_method,
}


def upgrade_router(econtext):
    if not isinstance(econtext.router, Router):  # TODO
        econtext.router.__class__ = Router  # TODO
        econtext.router.id_allocator = ChildIdAllocator(econtext.router)
        LOG.debug('_proxy_connect(): constructing ModuleForwarder')
        ModuleForwarder(econtext.router, econtext.parent, econtext.importer)


@mitogen.core.takes_econtext
def _proxy_connect(name, context_id, method_name, kwargs, econtext):
    upgrade_router(econtext)
    context = econtext.router._connect(
        context_id,
        METHOD_NAMES[method_name](),
        name=name,
        **kwargs
    )
    return context.name


class IdAllocator(object):
    def __init__(self, router):
        self.router = router
        self.next_id = 1
        self.lock = threading.Lock()
        router.add_handler(self.on_allocate_id, mitogen.core.ALLOCATE_ID)

    def __repr__(self):
        return 'IdAllocator(%r)' % (self.router,)

    def allocate(self):
        self.lock.acquire()
        try:
            id_ = self.next_id
            self.next_id += 1
            return id_
        finally:
            self.lock.release()

    def on_allocate_id(self, msg):
        id_ = self.allocate()
        requestee = self.router.context_by_id(msg.src_id)
        allocated = self.router.context_by_id(id_, msg.src_id)

        LOG.debug('%r: allocating %r to %r', self, allocated, requestee)
        self.router.route(
            mitogen.core.Message.pickled(
                id_,
                dst_id=msg.src_id,
                handle=msg.reply_to,
            )
        )

        LOG.debug('%r: publishing route to %r via %r', self,
                  allocated, requestee)
        self.router.propagate_route(allocated, requestee)


class ChildIdAllocator(object):
    def __init__(self, router):
        self.router = router

    def allocate(self):
        master = Context(self.router, 0)
        return master.send_await(
            mitogen.core.Message(dst_id=0, handle=mitogen.core.ALLOCATE_ID)
        )


class Router(mitogen.core.Router):
    broker_class = Broker
    debug = False

    profiling = False

    def __init__(self, broker=None):
        if broker is None:
            broker = self.broker_class()
        super(Router, self).__init__(broker)
        self.id_allocator = IdAllocator(self)
        self.responder = ModuleResponder(self)
        self.log_forwarder = LogForwarder(self)

    def enable_debug(self):
        mitogen.core.enable_debug_logging()
        self.debug = True

    def __enter__(self):
        return self

    def __exit__(self, e_type, e_val, tb):
        self.broker.shutdown()
        self.broker.join()

    def allocate_id(self):
        return self.id_allocator.allocate()

    def context_by_id(self, context_id, via_id=None):
        context = self._context_by_id.get(context_id)
        if context is None:
            context = Context(self, context_id)
            if via_id is not None:
                context.via = self.context_by_id(via_id)
            self._context_by_id[context_id] = context
        return context

    def local(self, **kwargs):
        return self.connect('local', **kwargs)

    def sudo(self, **kwargs):
        return self.connect('sudo', **kwargs)

    def ssh(self, **kwargs):
        return self.connect('ssh', **kwargs)

    def _connect(self, context_id, klass, name=None, **kwargs):
        context = Context(self, context_id)
        stream = klass(self, context.context_id, **kwargs)
        if name is not None:
            stream.name = name
        stream.connect()
        context.name = stream.name
        self.register(context, stream)
        return context

    def connect(self, method_name, name=None, **kwargs):
        klass = METHOD_NAMES[method_name]()
        kwargs.setdefault('debug', self.debug)
        kwargs.setdefault('profiling', self.profiling)

        via = kwargs.pop('via', None)
        if via is not None:
            return self.proxy_connect(via, method_name, name=name, **kwargs)
        context_id = self.allocate_id()
        return self._connect(context_id, klass, name=name, **kwargs)

    def propagate_route(self, target, via):
        self.add_route(target.context_id, via.context_id)
        child = via
        parent = via.via

        while parent is not None:
            LOG.debug('Adding route to %r for %r via %r', parent, target, child)
            parent.send(
                mitogen.core.Message(
                    data='%s\x00%s' % (target.context_id, child.context_id),
                    handle=mitogen.core.ADD_ROUTE,
                )
            )
            child = parent
            parent = parent.via

    def proxy_connect(self, via_context, method_name, name=None, **kwargs):
        context_id = self.allocate_id()
        # Must be added prior to _proxy_connect() to avoid a race.
        self.add_route(context_id, via_context.context_id)
        name = via_context.call(_proxy_connect,
            name, context_id, method_name, kwargs
        )
        name = '%s.%s' % (via_context.name, name)

        context = Context(self, context_id, name=name)
        context.via = via_context
        self._context_by_id[context.context_id] = context

        self.propagate_route(context, via_context)
        return context


class ProcessMonitor(object):
    def __init__(self):
        # pid -> callback()
        self.callback_by_pid = {}
        signal.signal(signal.SIGCHLD, self._on_sigchld)

    def _on_sigchld(self, _signum, _frame):
        for pid, callback in self.callback_by_pid.items():
            pid, status = os.waitpid(pid, os.WNOHANG)
            if pid:
                callback(status)
                del self.callback_by_pid[pid]

    def add(self, pid, callback):
        self.callback_by_pid[pid] = callback

    _instance = None

    @classmethod
    def instance(cls):
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance
