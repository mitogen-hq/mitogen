import os

import testlib


class ConstructorTest(testlib.RouterMixin, testlib.TestCase):
    def test_okay(self):
        docker_path = testlib.data_path('stubs/stub-docker.py')
        context = self.router.docker(
            container='container_name',
            docker_path=docker_path,
        )
        stream = self.router.stream_by_id(context.context_id)

        argv = eval(context.call(os.getenv, 'ORIGINAL_ARGV'))
        self.assertEqual(argv[0], docker_path)
        self.assertEqual(argv[1], 'exec')
        self.assertEqual(argv[2], '--interactive')
        self.assertEqual(argv[3], 'container_name')
        self.assertEqual(argv[4], stream.conn.options.python_path)
