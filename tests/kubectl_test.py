
import os

import mitogen
import mitogen.parent

import unittest2

import testlib


class ConstructorTest(testlib.RouterMixin, testlib.TestCase):
    kubectl_path = testlib.data_path('stubs/stub-kubectl.py')

    def test_okay(self):
        context = self.router.kubectl(
            pod='pod_name',
            kubectl_path=self.kubectl_path
        )

        argv = eval(context.call(os.getenv, 'ORIGINAL_ARGV'))
        self.assertEquals(argv[0], self.kubectl_path)
        self.assertEquals(argv[1], 'exec')
        self.assertEquals(argv[2], '-it')
        self.assertEquals(argv[3], 'pod_name')


if __name__ == '__main__':
    unittest2.main()
