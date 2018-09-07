import os
import sys

import mitogen
import mitogen.ssh
import mitogen.utils

import unittest2

import testlib
import plain_old_module


class FakeSshTest(testlib.RouterMixin, unittest2.TestCase):
    def test_okay(self):
        context = self.router.ssh(
            hostname='hostname',
            username='mitogen__has_sudo',
            ssh_path=testlib.data_path('fakessh.py'),
        )
        #context.call(mitogen.utils.log_to_file, '/tmp/log')
        #context.call(mitogen.utils.disable_site_packages)
        self.assertEquals(3, context.call(plain_old_module.add, 1, 2))


class SshTest(testlib.DockerMixin, unittest2.TestCase):
    stream_class = mitogen.ssh.Stream

    def test_stream_name(self):
        context = self.docker_ssh(
            username='mitogen__has_sudo',
            password='has_sudo_password',
        )
        name = 'ssh.%s:%s' % (
            self.dockerized_ssh.get_host(),
            self.dockerized_ssh.port,
        )
        self.assertEquals(name, context.name)

    def test_via_stream_name(self):
        context = self.docker_ssh(
            username='mitogen__has_sudo_nopw',
            password='has_sudo_nopw_password',
        )
        sudo = self.router.sudo(via=context)

        name = 'ssh.%s:%s.sudo.root' % (
            self.dockerized_ssh.host,
            self.dockerized_ssh.port,
        )
        self.assertEquals(name, sudo.name)

    def test_password_required(self):
        try:
            context = self.docker_ssh(
                username='mitogen__has_sudo',
            )
            assert 0, 'exception not thrown'
        except mitogen.ssh.PasswordError:
            e = sys.exc_info()[1]

        self.assertEqual(e.args[0], self.stream_class.password_required_msg)

    def test_password_incorrect(self):
        try:
            context = self.docker_ssh(
                username='mitogen__has_sudo',
                password='badpw',
            )
            assert 0, 'exception not thrown'
        except mitogen.ssh.PasswordError:
            e = sys.exc_info()[1]

        self.assertEqual(e.args[0], self.stream_class.password_incorrect_msg)

    def test_password_specified(self):
        context = self.docker_ssh(
            username='mitogen__has_sudo',
            password='has_sudo_password',
        )

        self.assertEqual(
            'i-am-mitogen-test-docker-image\n',
            context.call(plain_old_module.get_sentinel_value),
        )

    def test_pubkey_required(self):
        try:
            context = self.docker_ssh(
                username='mitogen__has_sudo_pubkey',
            )
            assert 0, 'exception not thrown'
        except mitogen.ssh.PasswordError:
            e = sys.exc_info()[1]

        self.assertEqual(e.args[0], self.stream_class.password_required_msg)

    def test_pubkey_specified(self):
        context = self.docker_ssh(
            username='mitogen__has_sudo_pubkey',
            identity_file=testlib.data_path('docker/mitogen__has_sudo_pubkey.key'),
        )
        self.assertEqual(
            'i-am-mitogen-test-docker-image\n',
            context.call(plain_old_module.get_sentinel_value),
        )


class BannerTest(testlib.DockerMixin, unittest2.TestCase):
    # Verify the ability to disambiguate random spam appearing in the SSHd's
    # login banner from a legitimate password prompt.
    stream_class = mitogen.ssh.Stream

    def test_verbose_enabled(self):
        context = self.docker_ssh(
            username='mitogen__has_sudo',
            password='has_sudo_password',
            ssh_debug_level=3,
        )
        name = 'ssh.%s:%s' % (
            self.dockerized_ssh.get_host(),
            self.dockerized_ssh.port,
        )
        self.assertEquals(name, context.name)


class BatchModeTest(testlib.DockerMixin, testlib.TestCase):
    stream_class = mitogen.ssh.Stream
    #
    # Test that:
    # 
    # - batch_mode=false, host_key_checking=accept
    # - batch_mode=false, host_key_checking=enforce
    # - batch_mode=false, host_key_checking=ignore
    #
    # - batch_mode=true, host_key_checking=accept
    # - batch_mode=true, host_key_checking=enforce
    # - batch_mode=true, host_key_checking=ignore
    # - batch_mode=true, password is not None
    # 
    def fake_ssh(self, FAKESSH_MODE=None, **kwargs):
        os.environ['FAKESSH_MODE'] = str(FAKESSH_MODE)
        try:
            return self.router.ssh(
                hostname='hostname',
                username='mitogen__has_sudo',
                ssh_path=testlib.data_path('fakessh.py'),
                **kwargs
            )
        finally:
            del os.environ['FAKESSH_MODE']

    def test_false_accept(self):
        # Should succeed.
        self.fake_ssh(FAKESSH_MODE='ask', check_host_keys='accept')

    def test_false_enforce(self):
        # Should succeed.
        self.fake_ssh(check_host_keys='enforce')

    def test_false_ignore(self):
        # Should succeed.
        self.fake_ssh(check_host_keys='ignore')

    def test_false_password(self):
        # Should succeed.
        self.docker_ssh(username='mitogen__has_sudo_nopw',
                        password='has_sudo_nopw_password')

    def test_true_accept(self):
        e = self.assertRaises(ValueError,
            lambda: self.fake_ssh(check_host_keys='accept', batch_mode=True)
        )
        self.assertEquals(e.args[0],
            self.stream_class.batch_mode_check_host_keys_msg)

    def test_true_enforce(self):
        e = self.assertRaises(mitogen.ssh.HostKeyError,
            lambda: self.docker_ssh(
                batch_mode=True,
                check_host_keys='enforce',
                ssh_args=['-o', 'UserKnownHostsFile /dev/null'],
            )
        )
        self.assertEquals(e.args[0], self.stream_class.hostkey_failed_msg)

    def test_true_ignore(self):
        e = self.assertRaises(mitogen.ssh.HostKeyError,
            lambda: self.fake_ssh(
                FAKESSH_MODE='strict',
                batch_mode=True,
                check_host_keys='ignore',
            )
        )
        self.assertEquals(e.args[0], self.stream_class.hostkey_failed_msg)

    def test_true_password(self):
        e = self.assertRaises(ValueError,
            lambda: self.fake_ssh(
                password='nope',
                batch_mode=True,
            )
        )
        self.assertEquals(e.args[0], self.stream_class.batch_mode_password_msg)



if __name__ == '__main__':
    unittest2.main()
