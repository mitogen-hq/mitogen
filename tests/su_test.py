
import getpass
import os

import mitogen
import mitogen.su

import unittest2

import testlib


class ConstructorTest(testlib.RouterMixin, testlib.TestCase):
    su_path = testlib.data_path('stubs/stub-su.py')

    def run_su(self, **kwargs):
        context = self.router.su(
            su_path=self.su_path,
            **kwargs
        )
        argv = eval(context.call(os.getenv, 'ORIGINAL_ARGV'))
        return context, argv

    def test_basic(self):
        context, argv = self.run_su()
        self.assertEquals(argv[1], 'root')
        self.assertEquals(argv[2], '-c')


class SuTest(testlib.DockerMixin, testlib.TestCase):
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
        self.assertEquals('root', context.call(getpass.getuser))


if __name__ == '__main__':
    unittest2.main()
