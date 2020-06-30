
import os

import mitogen
import mitogen.parent

import unittest2

import testlib


class ConstructorTest(testlib.RouterMixin, testlib.TestCase):
    chroot_exe = testlib.data_path('stubs/stub-chroot.py')

    def test_okay(self):
        context = self.router.chroot(
            chroot_exe=self.chroot_exe,
            container='somechroot',
        )
        stream = self.router.stream_by_id(context.context_id)

        argv = eval(context.call(os.getenv, 'ORIGINAL_ARGV'))
        self.assertEquals(argv[:4], [
            self.chroot_exe,
            'somechroot',
            stream.conn.options.python_path,
            '-c',
        ])
        self.assertEquals('1', context.call(os.getenv, 'THIS_IS_STUB_CHROOT'))


if __name__ == '__main__':
    unittest2.main()
