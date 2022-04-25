import os

import testlib


class ConstructorTest(testlib.RouterMixin, testlib.TestCase):
    kubectl_path = testlib.data_path('stubs/stub-kubectl.py')

    def test_okay(self):
        context = self.router.kubectl(
            pod='pod_name',
            kubectl_path=self.kubectl_path
        )

        argv = eval(context.call(os.getenv, 'ORIGINAL_ARGV'))
        self.assertEqual(argv[0], self.kubectl_path)
        self.assertEqual(argv[1], 'exec')
        self.assertEqual(argv[2], '-it')
        self.assertEqual(argv[3], 'pod_name')
