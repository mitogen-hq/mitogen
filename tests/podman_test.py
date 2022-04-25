import os

import testlib


class ConstructorTest(testlib.RouterMixin, testlib.TestCase):
    def test_okay(self):
        stub_path = testlib.data_path('stubs/stub-podman.py')

        context = self.router.podman(
            container='container_name',
            podman_path=stub_path,
        )
        stream = self.router.stream_by_id(context.context_id)

        argv = eval(context.call(os.getenv, 'ORIGINAL_ARGV'))
        expected_call = [
            stub_path,
            'exec',
            '--interactive',
            '--',
            'container_name',
            stream.conn.options.python_path
        ]
        self.assertEqual(argv[:len(expected_call)], expected_call)

        context = self.router.podman(
            container='container_name',
            podman_path=stub_path,
            username='some_user',
        )
        stream = self.router.stream_by_id(context.context_id)

        argv = eval(context.call(os.getenv, 'ORIGINAL_ARGV'))
        expected_call = [
            stub_path,
            'exec',
            '--user=some_user',
            '--interactive',
            '--',
            'container_name',
            stream.conn.options.python_path
        ]
        self.assertEqual(argv[:len(expected_call)], expected_call)
