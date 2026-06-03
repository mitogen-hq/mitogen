# -*- coding: utf-8 -*-
import os
import re

import testlib

import mitogen.core
import mitogen.sudo

class PasswordPromptTest(testlib.TestCase):
    def test_sudo_ws(self):
        self.assertTrue(mitogen.sudo.PASSWORD_PROMPT_RE.search(b'mitogen-sudo-prompt:'))

    def test_sudo_rs_en(self):
        self.assertTrue(mitogen.sudo.PASSWORD_PROMPT_RE.search(b'[sudo: mitogen-sudo-prompt:] Password: '))

    def test_sudo_rs_fr(self):
        # macOS+Ghostty 1.3.1-> ssh -> Ubuntu 26.04+sudo-rs -> LANGUAGE=fr sudo -k -p mitogen-sudo-prompt: true
        self.assertTrue(mitogen.sudo.PASSWORD_PROMPT_RE.search(u'[sudo: mitogen-sudo-prompt:] Mot de passe\N{NO-BREAK SPACE}: '.encode('utf-8')))
        # Possible future variation of translation
        self.assertTrue(mitogen.sudo.PASSWORD_PROMPT_RE.search(b'[sudo: mitogen-sudo-prompt:] Mot de passe : '))

    def test_sudo_rs_zh_CN(self):
        # macOS+Ghostty 1.3.1-> ssh -> Ubuntu 26.04+sudo-rs -> LANGUAGE=zh_CN sudo -k -p mitogen-sudo-prompt: true
        self.assertTrue(mitogen.sudo.PASSWORD_PROMPT_RE.search(u'[sudo: mitogen-sudo-prompt:] 密码： '.encode('utf-8')))


class PasswordPromptInProgressTest(testlib.TestCase):
    def test_empty_password_no_match(self):
        "A zero length password should not match the prompt again."
        self.assertIsNone(mitogen.sudo.PASSWORD_PROMPT_RE.search(b'mitogen-sudo-prompt:\n'))
        self.assertIsNone(mitogen.sudo.PASSWORD_PROMPT_RE.search(u'[sudo: mitogen-sudo-prompt:] Mot de passe\N{NO-BREAK SPACE}: \n'.encode('utf-8')))
        self.assertIsNone(mitogen.sudo.PASSWORD_PROMPT_RE.search(b'[sudo: mitogen-sudo-prompt:] Mot de passe : \n'))
        self.assertIsNone(mitogen.sudo.PASSWORD_PROMPT_RE.search(u'[sudo: mitogen-sudo-prompt:] 密码： \n'.encode('utf-8')))

    def test_pwfeedback_no_match(self):
        """
        Enabling pwfeedback (default in Ubuntu 26.04) shouldn't cause repeated
        matches of the prompt when '*' is echoed.
        """
        self.assertIsNone(mitogen.sudo.PASSWORD_PROMPT_RE.search(b'mitogen-sudo-prompt:*'))
        self.assertIsNone(mitogen.sudo.PASSWORD_PROMPT_RE.search(b'mitogen-sudo-prompt:*\n'))
        self.assertIsNone(mitogen.sudo.PASSWORD_PROMPT_RE.search(u'[sudo: mitogen-sudo-prompt:] Mot de passe\N{NO-BREAK SPACE}: *'.encode('utf-8')))
        self.assertIsNone(mitogen.sudo.PASSWORD_PROMPT_RE.search(u'[sudo: mitogen-sudo-prompt:] Mot de passe\N{NO-BREAK SPACE}: *\n'.encode('utf-8')))
        self.assertIsNone(mitogen.sudo.PASSWORD_PROMPT_RE.search(b'[sudo: mitogen-sudo-prompt:] Mot de passe : *'))
        self.assertIsNone(mitogen.sudo.PASSWORD_PROMPT_RE.search(b'[sudo: mitogen-sudo-prompt:] Mot de passe : *\n'))
        self.assertIsNone(mitogen.sudo.PASSWORD_PROMPT_RE.search(u'[sudo: mitogen-sudo-prompt:] 密码： *'.encode('utf-8')))
        self.assertIsNone(mitogen.sudo.PASSWORD_PROMPT_RE.search(u'[sudo: mitogen-sudo-prompt:] 密码： *\n'.encode('utf-8')))


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
        expected_argv_tail = [
            self.sudo_path,
            '-p', 'mitogen-sudo-prompt:',
            '-u', 'root',
            '--'
        ]
        self.assertEqual(argv[:len(expected_argv_tail)], expected_argv_tail)

    def test_selinux_type_role(self):
        context, argv = self.run_sudo(
            selinux_type='setype',
            selinux_role='serole',
        )
        expected_argv_tail = [
            self.sudo_path,
            '-p', 'mitogen-sudo-prompt:',
            '-u', 'root',
            '-r', 'serole',
            '-t', 'setype',
            '--'
        ]
        self.assertEqual(argv[:len(expected_argv_tail)], expected_argv_tail)

    def test_reparse_args(self):
        context, argv = self.run_sudo(
            sudo_args=['--type', 'setype', '--role', 'serole', '--user', 'user']
        )
        expected_argv_tail = [
            self.sudo_path,
            '-p', 'mitogen-sudo-prompt:',
            '-u', 'user',
            '-r', 'serole',
            '-t', 'setype',
            '--'
        ]
        self.assertEqual(argv[:len(expected_argv_tail)], expected_argv_tail)

    def test_tty_preserved(self):
        # issue #481
        os.environ['PREHISTORIC_SUDO'] = '1'
        try:
            context, argv = self.run_sudo()
            self.assertEqual('1', context.call(os.getenv, 'PREHISTORIC_SUDO'))
        finally:
            del os.environ['PREHISTORIC_SUDO']


class SudoMixin(testlib.DockerMixin):
    def test_password_required(self):
        ssh = self.docker_ssh(
            username='mitogen__has_sudo',
            password='has_sudo_password',
        )
        ssh.call(os.putenv, 'LANGUAGE', 'fr')
        ssh.call(os.putenv, 'LC_ALL', 'fr_FR.UTF-8')
        e = self.assertRaises(mitogen.core.StreamError,
            lambda: self.router.sudo(via=ssh)
        )
        self.assertIn(mitogen.sudo.password_required_msg, str(e))

    def test_password_incorrect(self):
        ssh = self.docker_ssh(
            username='mitogen__has_sudo',
            password='has_sudo_password',
        )
        ssh.call(os.putenv, 'LANGUAGE', 'fr')
        ssh.call(os.putenv, 'LC_ALL', 'fr_FR.UTF-8')
        e = self.assertRaises(mitogen.core.StreamError,
            lambda: self.router.sudo(via=ssh, password='x')
        )
        self.assertIn(mitogen.sudo.password_incorrect_msg, str(e))

    def test_password_okay(self):
        ssh = self.docker_ssh(
            username='mitogen__has_sudo',
            password='has_sudo_password',
        )
        ssh.call(os.putenv, 'LANGUAGE', 'fr')
        ssh.call(os.putenv, 'LC_ALL', 'fr_FR.UTF-8')
        e = self.assertRaises(mitogen.core.StreamError,
            lambda: self.router.sudo(via=ssh, password='rootpassword')
        )
        self.assertIn(mitogen.sudo.password_incorrect_msg, str(e))


for distro_spec in testlib.DISTRO_SPECS.split():
    # Only debian<version>-test images have translations installed/configured
    if not re.match('debian', distro_spec, re.IGNORECASE):
        continue

    dockerized_ssh = testlib.DockerizedSshDaemon(distro_spec)
    klass_name = 'SudoTest%s' % (dockerized_ssh.distro.capitalize(),)
    klass = type(
        klass_name,
        (SudoMixin, testlib.TestCase),
        {'dockerized_ssh': dockerized_ssh},
    )
    globals()[klass_name] = klass
