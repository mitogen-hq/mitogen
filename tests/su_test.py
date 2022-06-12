import os

import mitogen.core
import mitogen.su

import testlib


class ConstructorTest(testlib.RouterMixin, testlib.TestCase):
    stub_su_path = testlib.data_path('stubs/stub-su.py')

    def run_su(self, **kwargs):
        context = self.router.su(
            su_path=self.stub_su_path,
            **kwargs
        )
        argv = eval(context.call(os.getenv, 'ORIGINAL_ARGV'))
        return context, argv

    def test_basic(self):
        context, argv = self.run_su()
        self.assertEqual(argv[1], 'root')
        self.assertEqual(argv[2], '-c')


class SuTest(testlib.DockerMixin, testlib.TestCase):
    stub_su_path = testlib.data_path('stubs/stub-su.py')

    def test_slow_auth_failure(self):
        # #363: old input loop would fail to spot auth failure because of
        # scheduling vs. su calling write() twice.
        os.environ['DO_SLOW_AUTH_FAILURE'] = '1'
        try:
            self.assertRaises(mitogen.su.PasswordError,
                lambda: self.router.su(su_path=self.stub_su_path)
            )
        finally:
            del os.environ['DO_SLOW_AUTH_FAILURE']

    def test_password_required(self):
        ssh = self.docker_ssh(
            username='mitogen__has_sudo',
            password='has_sudo_password',
        )
        e = self.assertRaises(mitogen.core.StreamError,
            lambda: self.router.su(via=ssh)
        )
        self.assertTrue(mitogen.su.password_required_msg in str(e))

    def test_password_incorrect(self):
        ssh = self.docker_ssh(
            username='mitogen__has_sudo',
            password='has_sudo_password',
        )
        e = self.assertRaises(mitogen.core.StreamError,
            lambda: self.router.su(via=ssh, password='x')
        )
        self.assertTrue(mitogen.su.password_incorrect_msg in str(e))

    def test_password_okay(self):
        ssh = self.docker_ssh(
            username='mitogen__has_sudo',
            password='has_sudo_password',
        )
        context = self.router.su(via=ssh, password='rootpassword')
        self.assertEqual(0, context.call(os.getuid))
