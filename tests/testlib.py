
import logging
import os
import random
import re
import signal
import socket
import subprocess
import sys
import threading
import time
import traceback

import unittest2

import mitogen.core
import mitogen.fork
import mitogen.master
import mitogen.utils

try:
    import faulthandler
except ImportError:
    faulthandler = None

try:
    import urlparse
except ImportError:
    import urllib.parse as urlparse

try:
    from cStringIO import StringIO
except ImportError:
    from io import StringIO

try:
    BaseException
except NameError:
    BaseException = Exception


LOG = logging.getLogger(__name__)
DATA_DIR = os.path.join(os.path.dirname(__file__), 'data')
MODS_DIR = os.path.join(DATA_DIR, 'importer')

sys.path.append(DATA_DIR)
sys.path.append(MODS_DIR)


if mitogen.is_master:
    mitogen.utils.log_to_file()

if faulthandler is not None:
    faulthandler.enable()


#
# Temporary hack: Operon changed logging somewhat, and this broke LogCapturer /
# log_handler_test.
#

mitogen.core.LOG.propagate = True



def get_fd_count():
    """
    Return the number of FDs open by this process.
    """
    import psutil
    return psutil.Process().num_fds()


def data_path(suffix):
    path = os.path.join(DATA_DIR, suffix)
    if path.endswith('.key'):
        # SSH is funny about private key permissions.
        os.chmod(path, int('0600', 8))
    return path


def subprocess__check_output(*popenargs, **kwargs):
    # Missing from 2.6.
    process = subprocess.Popen(stdout=subprocess.PIPE, *popenargs, **kwargs)
    output, _ = process.communicate()
    retcode = process.poll()
    if retcode:
        cmd = kwargs.get("args")
        if cmd is None:
            cmd = popenargs[0]
        raise subprocess.CalledProcessError(retcode, cmd)
    return output


def Popen__terminate(proc):
    os.kill(proc.pid, signal.SIGTERM)


if hasattr(subprocess, 'check_output'):
    subprocess__check_output = subprocess.check_output

if hasattr(subprocess.Popen, 'terminate'):
    Popen__terminate = subprocess.Popen.terminate


def wait_for_port(
        host,
        port,
        pattern=None,
        connect_timeout=0.5,
        receive_timeout=0.5,
        overall_timeout=5.0,
        sleep=0.1,
        ):
    """Attempt to connect to host/port, for upto overall_timeout seconds.
    If a regex pattern is supplied try to find it in the initial data.
    Return None on success, or raise on error.
    """
    start = mitogen.core.now()
    end = start + overall_timeout
    addr = (host, port)

    while mitogen.core.now() < end:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(connect_timeout)
        try:
            sock.connect(addr)
        except socket.error:
            # Failed to connect. So wait then retry.
            time.sleep(sleep)
            continue

        if not pattern:
            # Success: We connected & there's no banner check to perform.
            sock.shutdown(socket.SHUTD_RDWR)
            sock.close()
            return

        sock.settimeout(receive_timeout)
        data = mitogen.core.b('')
        found = False
        while mitogen.core.now() < end:
            try:
                resp = sock.recv(1024)
            except socket.timeout:
                # Server stayed up, but had no data. Retry the recv().
                continue

            if not resp:
                # Server went away. Wait then retry the connection.
                time.sleep(sleep)
                break

            data += resp
            if re.search(mitogen.core.b(pattern), data):
                found = True
                break

        try:
            sock.shutdown(socket.SHUT_RDWR)
        except socket.error:
            e = sys.exc_info()[1]
            # On Mac OS X - a BSD variant - the above code only succeeds if the
            # operating system thinks that the socket is still open when
            # shutdown() is invoked. If Python is too slow and the FIN packet
            # arrives before that statement can be reached, then OS X kills the
            # sock.shutdown() statement with:
            #
            #    socket.error: [Errno 57] Socket is not connected
            #
            # Protect shutdown() with a try...except that catches the
            # socket.error, test to make sure Errno is right, and ignore it if
            # Errno matches.
            if e.errno == 57:
                pass
            else:
                raise
        sock.close()

        if found:
            # Success: We received the banner & found the desired pattern
            return
    else:
        # Failure: The overall timeout expired
        if pattern:
            raise socket.timeout('Timed out while searching for %r from %s:%s'
                                 % (pattern, host, port))
        else:
            raise socket.timeout('Timed out while connecting to %s:%s'
                                 % (host, port))


def sync_with_broker(broker, timeout=10.0):
    """
    Insert a synchronization barrier between the calling thread and the Broker
    thread, ensuring it has completed at least one full IO loop before
    returning.

    Used to block while asynchronous stuff (like defer()) happens on the
    broker.
    """
    sem = mitogen.core.Latch()
    broker.defer(sem.put, None)
    sem.get(timeout=timeout)


def log_fd_calls():
    mypid = os.getpid()
    l = threading.Lock()
    real_pipe = os.pipe
    def pipe():
        l.acquire()
        try:
            rv = real_pipe()
            if mypid == os.getpid():
                sys.stdout.write('\n%s\n' % (rv,))
                traceback.print_stack(limit=3)
                sys.stdout.write('\n')
            return rv
        finally:
            l.release()

    os.pipe = pipe

    real_socketpair = socket.socketpair
    def socketpair(*args):
        l.acquire()
        try:
            rv = real_socketpair(*args)
            if mypid == os.getpid():
                sys.stdout.write('\n%s -> %s\n' % (args, rv))
                traceback.print_stack(limit=3)
                sys.stdout.write('\n')
                return rv
        finally:
            l.release()

    socket.socketpair = socketpair

    real_dup2 = os.dup2
    def dup2(*args):
        l.acquire()
        try:
            real_dup2(*args)
            if mypid == os.getpid():
                sys.stdout.write('\n%s\n' % (args,))
                traceback.print_stack(limit=3)
                sys.stdout.write('\n')
        finally:
            l.release()

    os.dup2 = dup2

    real_dup = os.dup
    def dup(*args):
        l.acquire()
        try:
            rv = real_dup(*args)
            if mypid == os.getpid():
                sys.stdout.write('\n%s -> %s\n' % (args, rv))
                traceback.print_stack(limit=3)
                sys.stdout.write('\n')
            return rv
        finally:
            l.release()

    os.dup = dup


class CaptureStreamHandler(logging.StreamHandler):
    def __init__(self, *args, **kwargs):
        logging.StreamHandler.__init__(self, *args, **kwargs)
        self.msgs = []

    def emit(self, msg):
        self.msgs.append(msg)
        logging.StreamHandler.emit(self, msg)


class LogCapturer(object):
    def __init__(self, name=None):
        self.sio = StringIO()
        self.logger = logging.getLogger(name)
        self.handler = CaptureStreamHandler(self.sio)
        self.old_propagate = self.logger.propagate
        self.old_handlers = self.logger.handlers
        self.old_level = self.logger.level

    def start(self):
        self.logger.handlers = [self.handler]
        self.logger.propagate = False
        self.logger.level = logging.DEBUG

    def raw(self):
        s = self.sio.getvalue()
        # Python 2.x logging package hard-wires UTF-8 output.
        if isinstance(s, mitogen.core.BytesType):
            s = s.decode('utf-8')
        return s

    def msgs(self):
        return self.handler.msgs

    def __enter__(self):
        self.start()
        return self

    def __exit__(self, _1, _2, _3):
        self.stop()

    def stop(self):
        self.logger.level = self.old_level
        self.logger.handlers = self.old_handlers
        self.logger.propagate = self.old_propagate
        return self.raw()


class TestCase(unittest2.TestCase):
    @classmethod
    def setUpClass(cls):
        # This is done in setUpClass() so we have a chance to run before any
        # Broker() instantiations in setUp() etc.
        mitogen.fork.on_fork()
        cls._fd_count_before = get_fd_count()
        super(TestCase, cls).setUpClass()

    ALLOWED_THREADS = set([
        'MainThread',
        'mitogen.master.join_thread_async'
    ])

    def _teardown_check_threads(self):
        counts = {}
        for thread in threading.enumerate():
            name = thread.getName()
            # Python 2.4: enumerate() may return stopped threads.
            assert (not thread.isAlive()) or name in self.ALLOWED_THREADS, \
                'Found thread %r still running after tests.' % (name,)
            counts[name] = counts.get(name, 0) + 1

        for name in counts:
            assert counts[name] == 1, \
                'Found %d copies of thread %r running after tests.' % (
                    counts[name], name
                )

    def _teardown_check_fds(self):
        mitogen.core.Latch._on_fork()
        if get_fd_count() != self._fd_count_before:
            import os; os.system('lsof +E -w -p %s | grep -vw mem' % (os.getpid(),))
            assert 0, "%s leaked FDs. Count before: %s, after: %s" % (
                self, self._fd_count_before, get_fd_count(),
            )

    # Some class fixtures (like Ansible MuxProcess) start persistent children
    # for the duration of the class.
    no_zombie_check = False

    def _teardown_check_zombies(self):
        if self.no_zombie_check:
            return

        try:
            pid, status = os.waitpid(0, os.WNOHANG)
        except OSError:
            return  # ECHILD

        if pid:
            assert 0, "%s failed to reap subprocess %d (status %d)." % (
                self, pid, status
            )

        print('')
        print('Children of unit test process:')
        os.system('ps uww --ppid ' + str(os.getpid()))
        assert 0, "%s leaked still-running subprocesses." % (self,)

    def tearDown(self):
        self._teardown_check_zombies()
        self._teardown_check_threads()
        self._teardown_check_fds()
        super(TestCase, self).tearDown()

    def assertRaises(self, exc, func, *args, **kwargs):
        """Like regular assertRaises, except return the exception that was
        raised. Can't use context manager because tests must run on Python2.4"""
        try:
            func(*args, **kwargs)
        except exc:
            e = sys.exc_info()[1]
            return e
        except BaseException:
            LOG.exception('Original exception')
            e = sys.exc_info()[1]
            assert 0, '%r raised %r, not %r' % (func, e, exc)
        assert 0, '%r did not raise %r' % (func, exc)


def get_docker_host():
    url = os.environ.get('DOCKER_HOST')
    if url in (None, 'http+docker://localunixsocket'):
        return 'localhost'

    parsed = urlparse.urlparse(url)
    return parsed.netloc.partition(':')[0]


class DockerizedSshDaemon(object):
    def _get_container_port(self):
        s = subprocess__check_output(['docker', 'port', self.container_name])
        for line in s.decode().splitlines():
            dport, proto, baddr, bport = self.PORT_RE.match(line).groups()
            if dport == '22' and proto == 'tcp':
                self.port = int(bport)

        self.host = self.get_host()
        if self.port is None:
            raise ValueError('could not find SSH port in: %r' % (s,))

    def start_container(self):
        try:
            subprocess__check_output(['docker', '--version'])
        except Exception:
            raise unittest2.SkipTest('Docker binary is unavailable')

        self.container_name = 'mitogen-test-%08x' % (random.getrandbits(64),)
        args = [
            'docker',
            'run',
            '--detach',
            '--privileged',
            '--publish-all',
            '--name', self.container_name,
            self.image,
        ]
        subprocess__check_output(args)
        self._get_container_port()

    def __init__(self, mitogen_test_distro=os.environ.get('MITOGEN_TEST_DISTRO', 'debian')):
        if '-'  in mitogen_test_distro:
            distro, _py3 = mitogen_test_distro.split('-')
        else:
            distro = mitogen_test_distro
            _py3 = None

        if _py3 == 'py3':
            self.python_path = '/usr/bin/python3'
        else:
            self.python_path = '/usr/bin/python'

        self.image = 'mitogen/%s-test' % (distro,)

        # 22/tcp -> 0.0.0.0:32771
        self.PORT_RE = re.compile(r'([^/]+)/([^ ]+) -> ([^:]+):(.*)')
        self.port = None

        self.start_container()

    def get_host(self):
        return get_docker_host()

    def wait_for_sshd(self):
        wait_for_port(self.get_host(), self.port, pattern='OpenSSH')

    def check_processes(self):
        args = ['docker', 'exec', self.container_name, 'ps', '-o', 'comm=']
        counts = {}
        for comm in subprocess__check_output(args).decode().splitlines():
            comm = comm.strip()
            counts[comm] = counts.get(comm, 0) + 1

        if counts != {'ps': 1, 'sshd': 1}:
            assert 0, (
                'Docker container %r contained extra running processes '
                'after test completed: %r' % (
                    self.container_name,
                    counts
                )
            )

    def close(self):
        args = ['docker', 'rm', '-f', self.container_name]
        subprocess__check_output(args)


class BrokerMixin(object):
    broker_class = mitogen.master.Broker
    broker_shutdown = False

    def setUp(self):
        super(BrokerMixin, self).setUp()
        self.broker = self.broker_class()

    def tearDown(self):
        if not self.broker_shutdown:
            self.broker.shutdown()
        self.broker.join()
        del self.broker
        super(BrokerMixin, self).tearDown()

    def sync_with_broker(self):
        sync_with_broker(self.broker)


class RouterMixin(BrokerMixin):
    router_class = mitogen.master.Router

    def setUp(self):
        super(RouterMixin, self).setUp()
        self.router = self.router_class(self.broker)

    def tearDown(self):
        del self.router
        super(RouterMixin, self).tearDown()


class DockerMixin(RouterMixin):
    @classmethod
    def setUpClass(cls):
        super(DockerMixin, cls).setUpClass()
        if os.environ.get('SKIP_DOCKER_TESTS'):
            raise unittest2.SkipTest('SKIP_DOCKER_TESTS is set')

        # we want to be able to override test distro for some tests that need a different container spun up
        daemon_args = {}
        if hasattr(cls, 'mitogen_test_distro'):
            daemon_args['mitogen_test_distro'] = cls.mitogen_test_distro

        cls.dockerized_ssh = DockerizedSshDaemon(**daemon_args)
        cls.dockerized_ssh.wait_for_sshd()

    @classmethod
    def tearDownClass(cls):
        cls.dockerized_ssh.check_processes()
        cls.dockerized_ssh.close()
        super(DockerMixin, cls).tearDownClass()

    def docker_ssh(self, **kwargs):
        kwargs.setdefault('hostname', self.dockerized_ssh.host)
        kwargs.setdefault('port', self.dockerized_ssh.port)
        kwargs.setdefault('check_host_keys', 'ignore')
        kwargs.setdefault('ssh_debug_level', 3)
        kwargs.setdefault('python_path', self.dockerized_ssh.python_path)
        return self.router.ssh(**kwargs)

    def docker_ssh_any(self, **kwargs):
        return self.docker_ssh(
            username='mitogen__has_sudo_nopw',
            password='has_sudo_nopw_password',
        )
