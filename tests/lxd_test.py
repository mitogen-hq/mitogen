import os

import mitogen.lxd
import mitogen.parent

import testlib


class ConstructorTest(testlib.RouterMixin, testlib.TestCase):
    def test_okay(self):
        lxc_path = testlib.data_path('stubs/stub-lxc.py')
        context = self.router.lxd(
            container='container_name',
            lxc_path=lxc_path,
        )

        argv = eval(context.call(os.getenv, 'ORIGINAL_ARGV'))
        self.assertEqual(argv[0], lxc_path)
        self.assertEqual(argv[1], 'exec')
        self.assertEqual(argv[2], '--mode=noninteractive')
        self.assertEqual(argv[3], 'container_name')

    def test_eof(self):
        e = self.assertRaises(mitogen.parent.EofError,
            lambda: self.router.lxd(
                container='container_name',
                lxc_path='true',
            )
        )
        self.assertTrue(str(e).endswith(mitogen.lxd.Connection.eof_error_hint))
