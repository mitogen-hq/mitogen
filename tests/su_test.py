
import os

import mitogen
import mitogen.lxd
import mitogen.parent

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


if __name__ == '__main__':
    unittest2.main()
