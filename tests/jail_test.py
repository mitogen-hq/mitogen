
import os

import mitogen
import mitogen.parent

import unittest2

import testlib


class ConstructorTest(testlib.RouterMixin, testlib.TestCase):
    jexec_path = testlib.data_path('stubs/stub-jexec.py')

    def test_okay(self):
        context = self.router.jail(
            jexec_path=self.jexec_path,
            container='somejail',
        )
        stream = self.router.stream_by_id(context.context_id)

        argv = eval(context.call(os.getenv, 'ORIGINAL_ARGV'))
        self.assertEquals(argv[:4], [
            self.jexec_path,
            'somejail',
            stream.conn.options.python_path,
            '-c',
        ])
        self.assertEquals('1', context.call(os.getenv, 'THIS_IS_STUB_JEXEC'))


if __name__ == '__main__':
    unittest2.main()
