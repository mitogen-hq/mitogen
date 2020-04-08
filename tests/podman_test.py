import os

import mitogen

import unittest2

import testlib


class ConstructorTest(testlib.RouterMixin, testlib.TestCase):
    def test_okay(self):
        podman_path = testlib.data_path('stubs/stub-podman.py')
        context = self.router.podman(
            container='container_name',
            podman_path=podman_path,
        )
        stream = self.router.stream_by_id(context.context_id)

        argv = eval(context.call(os.getenv, 'ORIGINAL_ARGV'))
        self.assertEquals(argv[0], podman_path)
        self.assertEquals(argv[1], 'exec')
        self.assertEquals(argv[2], '--interactive')
        self.assertEquals(argv[3], 'container_name')
        self.assertEquals(argv[4], stream.conn.options.python_path)


if __name__ == '__main__':
    unittest2.main()
