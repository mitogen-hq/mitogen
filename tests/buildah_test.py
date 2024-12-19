import os

import testlib


class ConstructorTest(testlib.RouterMixin, testlib.TestCase):
    def test_okay(self):
        buildah_path = testlib.data_path('stubs/stub-buildah.py')
        context = self.router.buildah(
            container='container_name',
            buildah_path=buildah_path,
        )
        stream = self.router.stream_by_id(context.context_id)

        argv = eval(context.call(os.getenv, 'ORIGINAL_ARGV'))
        self.assertEqual(argv[0], buildah_path)
        self.assertEqual(argv[1], 'run')
        self.assertEqual(argv[2], '--')
        self.assertEqual(argv[3], 'container_name')
        self.assertEqual(argv[4], stream.conn.options.python_path)
