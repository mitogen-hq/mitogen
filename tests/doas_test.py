import os

import mitogen.core
import mitogen.doas

import testlib


class ConstructorTest(testlib.RouterMixin, testlib.TestCase):
    doas_path = testlib.data_path('stubs/stub-doas.py')

    def test_okay(self):
        context = self.router.doas(
            doas_path=self.doas_path,
            username='someuser',
        )
        argv = eval(context.call(os.getenv, 'ORIGINAL_ARGV'))
        self.assertEqual(argv[:4], [
            self.doas_path,
            '-u',
            'someuser',
            '--',
        ])
        self.assertEqual('1', context.call(os.getenv, 'THIS_IS_STUB_DOAS'))


# TODO: https://github.com/dw/mitogen/issues/694 they are flaky on python 2.6 MODE=mitogen DISTROS=centos7
# class DoasTest(testlib.DockerMixin, testlib.TestCase):
#     # Only mitogen/debian-test has doas.
#     mitogen_test_distro = 'debian'

#     def test_password_required(self):
#         ssh = self.docker_ssh(
#             username='mitogen__has_sudo',
#             password='has_sudo_password',
#         )
#         e = self.assertRaises(mitogen.core.StreamError,
#             lambda: self.router.doas(via=ssh)
#         )
#         self.assertTrue(mitogen.doas.password_required_msg in str(e))

#     def test_password_incorrect(self):
#         ssh = self.docker_ssh(
#             username='mitogen__has_sudo',
#             password='has_sudo_password',
#         )
#         e = self.assertRaises(mitogen.core.StreamError,
#             lambda: self.router.doas(via=ssh, password='x')
#         )
#         self.assertTrue(mitogen.doas.password_incorrect_msg in str(e))

#     def test_password_okay(self):
#         ssh = self.docker_ssh(
#             username='mitogen__has_sudo',
#             password='has_sudo_password',
#         )
#         context = self.router.doas(via=ssh, password='has_sudo_password')
#         self.assertEqual(0, context.call(os.getuid))
