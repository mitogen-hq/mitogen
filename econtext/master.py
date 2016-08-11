
import commands
import getpass
import inspect
import logging
import os
import pkgutil
import re
import socket
import sys
import textwrap
import zlib

import econtext.core


LOG = logging.getLogger('econtext')
IOLOG = logging.getLogger('econtext.io')
RLOG = logging.getLogger('econtext.ctx')

DOCSTRING_RE = re.compile(r'""".+?"""', re.M | re.S)
COMMENT_RE = re.compile(r'^\s*#.*$', re.M)


def MinimizeSource(source):
    subber = lambda match: '""' + ('\n' * match.group(0).count('\n'))
    source = DOCSTRING_RE.sub(subber, source)
    source = COMMENT_RE.sub('\n', source)
    return source.replace('    ', '\t')


def GetChildModules(module, prefix):
    it = pkgutil.iter_modules(module.__path__, prefix)
    return [name for _, name, _ in it]


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


class Listener(econtext.core.BasicStream):
    def __init__(self, broker, address=None, backlog=30):
        self._broker = broker
        self._sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._sock.bind(address or ('0.0.0.0', 0))
        self._sock.listen(backlog)
        econtext.core.set_cloexec(self._sock.fileno())
        self._listen_addr = self._sock.getsockname()
        self.read_side = econtext.core.Side(self, self._sock.fileno())
        broker.UpdateStream(self)

    def Receive(self):
        sock, addr = self._sock.accept()
        context = Context(self._broker, name=addr)
        stream = econtext.core.Stream(context)
        stream.Accept(sock.fileno(), sock.fileno())


class LogForwarder(object):
    def __init__(self, context):
        self._context = context
        self._context.AddHandleCB(self.ForwardLog,
                                  handle=econtext.core.FORWARD_LOG)
        self._log = RLOG.getChild(self._context.name)

    def ForwardLog(self, data):
        if data == econtext.core._DEAD:
            return

        name, level, s = data
        self._log.log(level, '%s: %s', name, s)


class ModuleResponder(object):
    def __init__(self, context):
        self._context = context
        self._context.AddHandleCB(self.GetModule,
                                  handle=econtext.core.GET_MODULE)

    def GetModule(self, data):
        if data == econtext.core._DEAD:
            return

        reply_to, fullname = data
        LOG.debug('GetModule(%r, %r)', reply_to, fullname)
        try:
            module = __import__(fullname, fromlist=[''])
            is_pkg = getattr(module, '__path__', None) is not None
            path = inspect.getsourcefile(module)
            try:
                source = inspect.getsource(module)
            except IOError:
                if not is_pkg:
                    raise
                source = '\n'

            if is_pkg:
                prefix = module.__name__ + '.'
                present = GetChildModules(module, prefix)
            else:
                present = None

            compressed = zlib.compress(MinimizeSource(source))
            reply = (is_pkg, present, path, compressed)
            self._context.Enqueue(reply_to, reply)
        except Exception:
            LOG.exception('While importing %r', fullname)
            self._context.Enqueue(reply_to, None)


class LocalStream(econtext.core.Stream):
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
            raise econtext.core.StreamError(
                '%r attempted to unpickle %r in module %r',
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
        name = self._context.remote_name
        if name is None:
            name = '%s@%s:%d'
            name %= (getpass.getuser(), socket.gethostname(), os.getpid())

        source = inspect.getsource(self._FirstStage)
        source = textwrap.dedent('\n'.join(source.strip().split('\n')[1:]))
        source = source.replace('    ', '\t')
        source = source.replace('CONTEXT_NAME', repr(name))
        encoded = source.encode('base64').replace('\n', '')
        return [self.python_path, '-c',
                'exec "%s".decode("base64")' % (encoded,)]

    def __repr__(self):
        return '%s(%s)' % (self.__class__.__name__, self._context)

    def GetPreamble(self):
        source = inspect.getsource(econtext.core)
        source += '\nExternalContext().main%r\n' % ((
            self._context.key,
            LOG.level or logging.getLogger().level or logging.INFO,
        ),)

        compressed = zlib.compress(MinimizeSource(source))
        return str(len(compressed)) + '\n' + compressed

    def Connect(self):
        LOG.debug('%r.Connect()', self)
        pid, sock = CreateChild(*self.GetBootCommand())
        self.read_side = econtext.core.Side(self, os.dup(sock.fileno()))
        self.write_side = self.read_side
        sock.close()
        LOG.debug('%r.Connect(): child process stdin/stdout=%r',
                  self, self.read_side.fd)

        econtext.core.write_all(self.write_side.fd, self.GetPreamble())
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


class Broker(econtext.core.Broker):
    def CreateListener(self, address=None, backlog=30):
        """Listen on `address `for connections from newly spawned contexts."""
        self._listener = Listener(self, address, backlog)

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
            name = hostname

        context = Context(self, name, hostname, username)
        context.stream = SSHStream(context)
        if python_path:
            context.stream.python_path = python_path
        context.stream.Connect()
        return self.Register(context)


class Context(econtext.core.Context):
    def __init__(self, *args, **kwargs):
        super(Context, self).__init__(*args, **kwargs)
        self.responder = ModuleResponder(self)
        self.log_forwarder = LogForwarder(self)

    def Disconnect(self):
        self.stream = None
