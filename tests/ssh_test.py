
import unittest

import mitogen
import mitogen.master
import mitogen.ssh
import mitogen.utils

import testlib


def add(x, y):
    return x + y


def get_sentinel_value():
    # Some proof we're even talking to the mitogen-test Docker image
    return file('/etc/sentinel').read()


class FakeSshTest(testlib.RouterMixin):
    def test_okay(router, self):
        def test(broker):
            context = mitogen.ssh.connect(broker,
                hostname='hostname',
                ssh_path=testlib.data_path('fakessh.py'))
            context.call(mitogen.utils.log_to_file, '/tmp/log')
            context.call(mitogen.utils.disable_site_packages)
            self.assertEquals(3, context.call(add, 1, 2))


class SshTest(testlib.DockerMixin, unittest.TestCase):
    stream_class = mitogen.ssh.Stream

    def test_password_required(self):
        try:
            context = self.router.ssh(
                hostname=self.dockerized_ssh.host,
                port=self.dockerized_ssh.port,
                check_host_keys=False,
                username='has-sudo',
            )
            assert 0, 'exception not thrown'
        except mitogen.ssh.PasswordError, e:
            pass

        assert e[0] == self.stream_class.password_required_msg

    def test_password_incorrect(self):
        try:
            context = self.router.ssh(
                hostname=self.dockerized_ssh.host,
                port=self.dockerized_ssh.port,
                check_host_keys=False,
                username='has-sudo',
                password='badpw',
            )
            assert 0, 'exception not thrown'
        except mitogen.ssh.PasswordError, e:
            pass

        assert e[0] == self.stream_class.password_incorrect_msg

    def test_password_specified(self):
        context = self.router.ssh(
            hostname=self.dockerized_ssh.host,
            port=self.dockerized_ssh.port,
            check_host_keys=False,
            username='has-sudo',
            password='y',
        )

        sentinel = 'i-am-mitogen-test-docker-image\n'
        assert sentinel == context.call(get_sentinel_value)

    def test_pubkey_required(self):
        try:
            context = self.router.ssh(
                hostname=self.dockerized_ssh.host,
                port=self.dockerized_ssh.port,
                check_host_keys=False,
                username='has-sudo-pubkey',
            )
            assert 0, 'exception not thrown'
        except mitogen.ssh.PasswordError, e:
            pass

        assert e[0] == self.stream_class.password_required_msg

    def test_pubkey_specified(self):
        try:
            context = self.router.ssh(
                hostname=self.dockerized_ssh.host,
                port=self.dockerized_ssh.port,
                check_host_keys=False,
                username='has-sudo-pubkey',
                identity_file=testlib.data_path('docker/has-sudo-pubkey.key'),
            )
            assert 0, 'exception not thrown'
        except mitogen.ssh.PasswordError, e:
            pass

        assert e[0] == self.stream_class.password_required_msg
