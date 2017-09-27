
import os
import random
import sys
import unittest
import urlparse

import mock

import mitogen.master
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


class DockerizedSshDaemon(object):
    def __init__(self):
        self.docker = docker.from_env()
        self.container_name = 'mitogen-test-%08x' % (random.getrandbits(64),)
        self.container = self.docker.containers.run(
            image='d2mw/mitogen-test',
            detach=True,
            remove=True,
            publish_all_ports=True,
        )
        self.container.reload()
        self.port = (self.container.attrs['NetworkSettings']['Ports']
                                         ['22/tcp'][0]['HostPort'])
        self.host = self.get_host()

    def get_host(self):
        parsed = urlparse.urlparse(self.docker.api.base_url)
        return parsed.netloc.partition(':')[0]

    def close(self):
        self.container.stop()


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
