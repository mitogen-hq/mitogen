import os

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
        self.assertEqual(argv[:4], [
            self.jexec_path,
            'somejail',
            stream.conn.options.python_path,
            '-c',
        ])
        self.assertEqual('1', context.call(os.getenv, 'THIS_IS_STUB_JEXEC'))
