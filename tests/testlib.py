
import os
import random
import re
import socket
import sys
import time
import unittest
import urlparse

import mitogen.master
if mitogen.is_master:  # TODO: shouldn't be necessary.
    import docker


DATA_DIR = os.path.join(os.path.dirname(__file__), 'data')
sys.path.append(DATA_DIR)


def set_debug():
    import logging
    logging.getLogger('mitogen').setLevel(logging.DEBUG)


def data_path(suffix):
    path = os.path.join(DATA_DIR, suffix)
    if path.endswith('.key'):
        # SSH is funny about private key permissions.
        os.chmod(path, 0600)
    return path


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
    start = time.time()
    end = start + overall_timeout
    addr = (host, port)

    while time.time() < end:
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
        data = ''
        found = False
        while time.time() < end:
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
            if re.search(pattern, data):
                found = True
                break

        try:
            sock.shutdown(socket.SHUT_RDWR)
        except socket.error, e:
            # On Mac OS X - a BSD variant - the above code only succeeds if the operating system thinks that the
            # socket is still open when shutdown() is invoked. If Python is too slow and the FIN packet arrives
            # before that statement can be reached, then OS X kills the sock.shutdown() statement with:
            #
            #    socket.error: [Errno 57] Socket is not connected
            #
            # Protect shutdown() with a try...except that catches the socket.error, test to make sure Errno is
            # right, and ignore it if Errno matches.
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


class TestCase(unittest.TestCase):
    def assertRaises(self, exc, func, *args, **kwargs):
        """Like regular assertRaises, except return the exception that was
        raised. Can't use context manager because tests must run on Python2.4"""
        try:
            func(*args, **kwargs)
        except exc, e:
            return e
        except BaseException, e:
            assert 0, '%r raised %r, not %r' % (func, e, exc)
        assert 0, '%r did not raise %r' % (func, exc)

    def assertContains(self, needle, hay):
        assert needle in hay, "%r not found in %r" % (needle, hay)


class DockerizedSshDaemon(object):
    def __init__(self):
        self.docker = docker.from_env(version='auto')
        self.container_name = 'mitogen-test-%08x' % (random.getrandbits(64),)
        self.container = self.docker.containers.run(
            image='d2mw/mitogen-test',
            detach=True,
            publish_all_ports=True,
        )
        self.container.reload()
        self.port = (self.container.attrs['NetworkSettings']['Ports']
                                         ['22/tcp'][0]['HostPort'])
        self.host = self.get_host()

    def get_host(self):
        if self.docker.api.base_url == 'http+docker://localunixsocket':
            return 'localhost'

        parsed = urlparse.urlparse(self.docker.api.base_url)
        return parsed.netloc.partition(':')[0]

    def wait_for_sshd(self):
        wait_for_port(self.get_host(), int(self.port), pattern='OpenSSH')

    def close(self):
        self.container.stop()
        self.container.remove()


class RouterMixin(object):
    broker_class = mitogen.master.Broker
    router_class = mitogen.master.Router

    def setUp(self):
        super(RouterMixin, self).setUp()
        self.broker = self.broker_class()
        self.router = self.router_class(self.broker)

    def tearDown(self):
        self.broker.shutdown()
        self.broker.join()
        super(RouterMixin, self).tearDown()


class DockerMixin(RouterMixin):
    @classmethod
    def setUpClass(cls):
        super(DockerMixin, cls).setUpClass()
        cls.dockerized_ssh = DockerizedSshDaemon()
        cls.dockerized_ssh.wait_for_sshd()

    @classmethod
    def tearDownClass(cls):
        cls.dockerized_ssh.close()
        super(DockerMixin, cls).tearDownClass()

    def docker_ssh(self, **kwargs):
        kwargs.setdefault('hostname', self.dockerized_ssh.host)
        kwargs.setdefault('port', self.dockerized_ssh.port)
        kwargs.setdefault('check_host_keys', False)
        return self.router.ssh(**kwargs)

    def docker_ssh_any(self, **kwargs):
        return self.docker_ssh(
            username='has-sudo-nopw',
            password='y',
        )
