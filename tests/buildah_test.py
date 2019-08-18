import os

import mitogen

import unittest2

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
        self.assertEquals(argv[0], buildah_path)
        self.assertEquals(argv[1], 'run')
        self.assertEquals(argv[2], '--')
        self.assertEquals(argv[3], 'container_name')
        self.assertEquals(argv[4], stream.conn.options.python_path)


if __name__ == '__main__':
    unittest2.main()
