import os
import tempfile

import mitogen.ssh
import mitogen.utils

import testlib
import plain_old_module


class StubSshMixin(testlib.RouterMixin):
    """
    Mix-in that provides :meth:`stub_ssh` executing the stub 'ssh.py'.
    """
    def stub_ssh(self, STUBSSH_MODE=None, **kwargs):
        os.environ['STUBSSH_MODE'] = str(STUBSSH_MODE)
        try:
            return self.router.ssh(
                hostname='hostname',
                username='mitogen__has_sudo',
                ssh_path=testlib.data_path('stubs/stub-ssh.py'),
                **kwargs
            )
        finally:
            del os.environ['STUBSSH_MODE']


class ConstructorTest(testlib.RouterMixin, testlib.TestCase):
    def test_okay(self):
        context = self.router.ssh(
            hostname='hostname',
            username='mitogen__has_sudo',
            ssh_path=testlib.data_path('stubs/stub-ssh.py'),
        )
        #context.call(mitogen.utils.log_to_file, '/tmp/log')
        #context.call(mitogen.utils.disable_site_packages)
        self.assertEqual(3, context.call(plain_old_module.add, 1, 2))


class SshTest(testlib.DockerMixin, testlib.TestCase):
    def test_debug_decoding(self):
        # ensure filter_debug_logs() decodes the logged string.
        capture = testlib.LogCapturer()
        capture.start()
        try:
            context = self.docker_ssh(
                username='mitogen__has_sudo',
                password='has_sudo_password',
                ssh_debug_level=3,
            )
        finally:
            s = capture.stop()

        expect = "%s: debug1: Reading configuration data" % (context.name,)
        self.assertIn(expect, s)

    def test_bash_permission_denied(self):
        # issue #271: only match Permission Denied at start of line.
        context = self.docker_ssh(
            username='mitogen__permdenied',
            password='permdenied_password',
            ssh_debug_level=3,
        )

    def test_stream_name(self):
        context = self.docker_ssh(
            username='mitogen__has_sudo',
            password='has_sudo_password',
        )
        name = 'ssh.%s:%s' % (
            self.dockerized_ssh.get_host(),
            self.dockerized_ssh.port,
        )
        self.assertEqual(name, context.name)

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
        self.assertEqual(name, sudo.name)

    def test_password_required(self):
        e = self.assertRaises(mitogen.ssh.PasswordError,
            lambda: self.docker_ssh(
                username='mitogen__has_sudo',
            )
        )
        self.assertEqual(e.args[0], mitogen.ssh.password_required_msg)

    def test_password_incorrect(self):
        e = self.assertRaises(mitogen.ssh.PasswordError,
            lambda: self.docker_ssh(
                username='mitogen__has_sudo',
                password='badpw',
            )
        )
        self.assertEqual(e.args[0], mitogen.ssh.password_incorrect_msg)

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
        e = self.assertRaises(mitogen.ssh.PasswordError,
            lambda: self.docker_ssh(
                username='mitogen__has_sudo_pubkey',
            )
        )
        self.assertEqual(e.args[0], mitogen.ssh.password_required_msg)

    def test_pubkey_specified(self):
        context = self.docker_ssh(
            username='mitogen__has_sudo_pubkey',
            identity_file=testlib.data_path('docker/mitogen__has_sudo_pubkey.key'),
        )
        self.assertEqual(
            'i-am-mitogen-test-docker-image\n',
            context.call(plain_old_module.get_sentinel_value),
        )

    def test_enforce_unknown_host_key(self):
        fp = tempfile.NamedTemporaryFile()
        ssh_args = self.docker_ssh_default_kwargs.get('ssh_args', [])
        try:
            e = self.assertRaises(mitogen.ssh.HostKeyError,
                lambda: self.docker_ssh(
                    username='mitogen__has_sudo_pubkey',
                    password='has_sudo_password',
                    ssh_args=ssh_args + ['-o', 'UserKnownHostsFile %s' % fp.name],
                    check_host_keys='enforce',
                )
            )
            self.assertEqual(e.args[0], mitogen.ssh.hostkey_failed_msg)
        finally:
            fp.close()

    def test_accept_enforce_host_keys(self):
        fp = tempfile.NamedTemporaryFile()
        ssh_args = self.docker_ssh_default_kwargs.get('ssh_args', [])
        try:
            context = self.docker_ssh(
                username='mitogen__has_sudo',
                password='has_sudo_password',
                ssh_args=ssh_args + ['-o', 'UserKnownHostsFile %s' % fp.name],
                check_host_keys='accept',
            )
            context.shutdown(wait=True)

            fp.seek(0)
            # Lame test, but we're about to use enforce mode anyway, which
            # verifies the file contents.
            self.assertGreater(len(fp.read()), 0)

            context = self.docker_ssh(
                username='mitogen__has_sudo',
                password='has_sudo_password',
                ssh_args=ssh_args + ['-o', 'UserKnownHostsFile %s' % fp.name],
                check_host_keys='enforce',
            )
            context.shutdown(wait=True)
        finally:
            fp.close()


class BannerTest(testlib.DockerMixin, testlib.TestCase):
    # Verify the ability to disambiguate random spam appearing in the SSHd's
    # login banner from a legitimate password prompt.
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
        self.assertEqual(name, context.name)


class StubPermissionDeniedTest(StubSshMixin, testlib.TestCase):
    def test_classic_prompt(self):
        self.assertRaises(mitogen.ssh.PasswordError,
            lambda: self.stub_ssh(STUBSSH_MODE='permdenied_classic'))

    def test_openssh_75_prompt(self):
        self.assertRaises(mitogen.ssh.PasswordError,
            lambda: self.stub_ssh(STUBSSH_MODE='permdenied_75'))


class StubCheckHostKeysTest(StubSshMixin, testlib.TestCase):
    def test_check_host_keys_accept(self):
        # required=true, host_key_checking=accept
        context = self.stub_ssh(STUBSSH_MODE='ask', check_host_keys='accept')
        self.assertEqual('1', context.call(os.getenv, 'STDERR_WAS_TTY'))

    def test_check_host_keys_enforce(self):
        # required=false, host_key_checking=enforce
        context = self.stub_ssh(check_host_keys='enforce')
        self.assertEqual(None, context.call(os.getenv, 'STDERR_WAS_TTY'))

    def test_check_host_keys_ignore(self):
        # required=false, host_key_checking=ignore
        context = self.stub_ssh(check_host_keys='ignore')
        self.assertEqual(None, context.call(os.getenv, 'STDERR_WAS_TTY'))

    def test_password_present(self):
        # required=true, password is not None
        context = self.stub_ssh(check_host_keys='ignore', password='willick')
        self.assertEqual('1', context.call(os.getenv, 'STDERR_WAS_TTY'))
