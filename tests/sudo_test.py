import os
import re

import mitogen.sudo

import testlib


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


class PasswordPromptPatternTest(testlib.TestCase):
    def _make_options(self, **kwargs):
        return mitogen.sudo.Options(
            max_message_size=mitogen.core.CHUNK_SIZE,
            **kwargs
        )

    def test_default_has_no_custom_prompt(self):
        options = self._make_options()
        self.assertIsNone(options.password_prompt)

    def test_custom_prompt_stored(self):
        options = self._make_options(
            password_prompt=r'\[sudo\] \w+@[\w.]+:',
        )
        self.assertEqual(options.password_prompt, r'\[sudo\] \w+@[\w.]+:')

    def test_custom_protocol_prepends_pattern(self):
        options = self._make_options(
            password_prompt=r'\[sudo\] \w+@[\w.]+:',
        )
        conn = mitogen.sudo.Connection(options, router=None)
        stream = conn.stderr_stream_factory()
        patterns = stream.protocol.PARTIAL_PATTERNS
        # custom pattern first, built-in second
        self.assertEqual(len(patterns), 2)
        self.assertEqual(patterns[0][0].pattern, b'\\[sudo\\] \\w+@[\\w.]+:')
        self.assertIs(patterns[1][0], mitogen.sudo.PASSWORD_PROMPT_RE)

    def test_no_custom_uses_default_protocol(self):
        options = self._make_options()
        conn = mitogen.sudo.Connection(options, router=None)
        stream = conn.stderr_stream_factory()
        self.assertIsInstance(stream.protocol, mitogen.sudo.SetupProtocol)
        self.assertEqual(len(stream.protocol.PARTIAL_PATTERNS), 1)


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
