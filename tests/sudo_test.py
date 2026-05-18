import os
import re

import testlib

import mitogen.core
import mitogen.sudo

class PasswordPromptTest(testlib.TestCase):
    def test_matches(self):
        # macOS 26.4.1, en_GB
        self.assertTrue(mitogen.sudo.PASSWORD_PROMPT_RE.search(b'Password:'))
        # Ubuntu 24.04, sudo-ws, en_GB
        self.assertTrue(mitogen.sudo.PASSWORD_PROMPT_RE.search(b'[sudo] password for alex: '))
        # Ubuntu 26.04, sudo-rs, en_GB
        self.assertTrue(mitogen.sudo.PASSWORD_PROMPT_RE.search(b'[sudo: authenticate] Password: '))

    def test_translated_matches(self):
        # Using French translation(s) as a stand-in for all translations.
        # RHEL 8, sudo-ws
        self.assertTrue(mitogen.sudo.PASSWORD_PROMPT_RE.search(b'Mot de passe de US3RN4ME:'))
        # Ubuntu 24.04, sudo-ws, fr_FR.UTF-8
        self.assertTrue(mitogen.sudo.PASSWORD_PROMPT_RE.search(b'[sudo] Mot de passe de alex : '))
        # Ubuntu 26.04, sudo-rs, fr_FR.UTF-8
        self.assertTrue(mitogen.sudo.PASSWORD_PROMPT_RE.search(b'[sudo: authenticate] Mot de passe : '))


class PasswordPromptInProgressTest(testlib.TestCase):
    def test_empty_password_no_match(self):
        "A zero length password should not match the prompt again."
        self.assertIsNone(mitogen.sudo.PASSWORD_PROMPT_RE.search(b'Password:\n'))
        self.assertIsNone(mitogen.sudo.PASSWORD_PROMPT_RE.search(b'[sudo: authenticate] Password: \n'))

    def test_pwfeedback_no_match(self):
        """
        Enabling pwfeedback (default in Ubuntu 26.04) shouldn't cause repeated
        matches of the prompt when '*' is echoed.
        """
        self.assertIsNone(mitogen.sudo.PASSWORD_PROMPT_RE.search(b'Password:*'))
        self.assertIsNone(mitogen.sudo.PASSWORD_PROMPT_RE.search(b'Password:*\n'))
        self.assertIsNone(mitogen.sudo.PASSWORD_PROMPT_RE.search(b'[sudo: authenticate] Password: *'))
        self.assertIsNone(mitogen.sudo.PASSWORD_PROMPT_RE.search(b'[sudo: authenticate] Password: *\n'))


class ConstructorTest(testlib.RouterMixin, testlib.TestCase):
    sudo_path = testlib.data_path('stubs/stub-sudo.py')

    def run_sudo(self, **kwargs):
        context = self.router.sudo(
            sudo_path=self.sudo_path,
            **kwargs
        )
        argv = eval(context.call(os.getenv, 'ORIGINAL_ARGV'))
        return context, argv


    def test_basic(self):
        context, argv = self.run_sudo()
        self.assertEqual(argv[:4], [
            self.sudo_path,
            '-u', 'root',
            '--'
        ])

    def test_selinux_type_role(self):
        context, argv = self.run_sudo(
            selinux_type='setype',
            selinux_role='serole',
        )
        self.assertEqual(argv[:8], [
            self.sudo_path,
            '-u', 'root',
            '-r', 'serole',
            '-t', 'setype',
            '--'
        ])

    def test_reparse_args(self):
        context, argv = self.run_sudo(
            sudo_args=['--type', 'setype', '--role', 'serole', '--user', 'user']
        )
        self.assertEqual(argv[:8], [
            self.sudo_path,
            '-u', 'user',
            '-r', 'serole',
            '-t', 'setype',
            '--'
        ])

    def test_tty_preserved(self):
        # issue #481
        os.environ['PREHISTORIC_SUDO'] = '1'
        try:
            context, argv = self.run_sudo()
            self.assertEqual('1', context.call(os.getenv, 'PREHISTORIC_SUDO'))
        finally:
            del os.environ['PREHISTORIC_SUDO']


# TODO: https://github.com/dw/mitogen/issues/694
# class NonEnglishPromptTest(testlib.DockerMixin, testlib.TestCase):
#     # Only mitogen/debian-test has a properly configured sudo.
#     mitogen_test_distro = 'debian'

#     def test_password_required(self):
#         ssh = self.docker_ssh(
#             username='mitogen__has_sudo',
#             password='has_sudo_password',
#         )
#         ssh.call(os.putenv, 'LANGUAGE', 'fr')
#         ssh.call(os.putenv, 'LC_ALL', 'fr_FR.UTF-8')
#         e = self.assertRaises(mitogen.core.StreamError,
#             lambda: self.router.sudo(via=ssh)
#         )
#         self.assertIn(mitogen.sudo.password_required_msg, str(e))

#     def test_password_incorrect(self):
#         ssh = self.docker_ssh(
#             username='mitogen__has_sudo',
#             password='has_sudo_password',
#         )
#         ssh.call(os.putenv, 'LANGUAGE', 'fr')
#         ssh.call(os.putenv, 'LC_ALL', 'fr_FR.UTF-8')
#         e = self.assertRaises(mitogen.core.StreamError,
#             lambda: self.router.sudo(via=ssh, password='x')
#         )
#         self.assertIn(mitogen.sudo.password_incorrect_msg, str(e))

#     def test_password_okay(self):
#         ssh = self.docker_ssh(
#             username='mitogen__has_sudo',
#             password='has_sudo_password',
#         )
#         ssh.call(os.putenv, 'LANGUAGE', 'fr')
#         ssh.call(os.putenv, 'LC_ALL', 'fr_FR.UTF-8')
#         e = self.assertRaises(mitogen.core.StreamError,
#             lambda: self.router.sudo(via=ssh, password='rootpassword')
#         )
#         self.assertIn(mitogen.sudo.password_incorrect_msg, str(e))
