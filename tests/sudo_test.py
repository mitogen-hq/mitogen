
import os

import mitogen
import mitogen.lxd
import mitogen.parent

import unittest2

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
        self.assertEquals(argv[:4], [
            self.sudo_path,
            '-u', 'root',
            '--'
        ])

    def test_selinux_type_role(self):
        context, argv = self.run_sudo(
            selinux_type='setype',
            selinux_role='serole',
        )
        self.assertEquals(argv[:8], [
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
        self.assertEquals(argv[:8], [
            self.sudo_path,
            '-u', 'user',
            '-r', 'serole',
            '-t', 'setype',
            '--'
        ])


if __name__ == '__main__':
    unittest2.main()
