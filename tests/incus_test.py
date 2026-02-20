import os

import mitogen.incus
import mitogen.parent

import testlib


class ConstructorTest(testlib.RouterMixin, testlib.TestCase):
    def test_okay(self):
        incus_path = testlib.data_path('stubs/stub-incus.py')
        context = self.router.incus(
            container='container_name',
            incus_path=incus_path,
        )

        argv = eval(context.call(os.getenv, 'ORIGINAL_ARGV'))
        self.assertEqual(argv[0], incus_path)
        self.assertEqual(argv[1], 'exec')
        self.assertEqual(argv[2], '--mode=non-interactive')
        self.assertEqual(argv[3], 'container_name')

    def test_eof(self):
        e = self.assertRaises(mitogen.parent.EofError,
            lambda: self.router.incus(
                container='container_name',
                incus_path='true',
            )
        )
        self.assertTrue(str(e).endswith(mitogen.incus.Connection.eof_error_hint))
