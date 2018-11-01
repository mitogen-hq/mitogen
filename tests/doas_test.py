
import os

import mitogen
import mitogen.parent

import unittest2

import testlib


class ConstructorTest(testlib.RouterMixin, testlib.TestCase):
    doas_path = testlib.data_path('stubs/stub-doas.py')

    def test_okay(self):
        context = self.router.doas(
            doas_path=self.doas_path,
            username='someuser',
        )
        argv = eval(context.call(os.getenv, 'ORIGINAL_ARGV'))
        self.assertEquals(argv[:4], [
            self.doas_path,
            '-u',
            'someuser',
            '--',
        ])
        self.assertEquals('1', context.call(os.getenv, 'THIS_IS_STUB_DOAS'))


if __name__ == '__main__':
    unittest2.main()
