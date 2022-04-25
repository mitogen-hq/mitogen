import os

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
#         self.assertTrue(mitogen.sudo.password_required_msg in str(e))

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
#         self.assertTrue(mitogen.sudo.password_incorrect_msg in str(e))

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
#         self.assertTrue(mitogen.sudo.password_incorrect_msg in str(e))
