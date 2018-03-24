
import os

import mitogen
import unittest2

import testlib
import plain_old_module


class ForkTest(testlib.RouterMixin, unittest2.TestCase):
    def test_okay(self):
        context = self.router.fork()
        self.assertNotEqual(context.call(os.getpid), os.getpid())
        self.assertEqual(context.call(os.getppid), os.getpid())


if __name__ == '__main__':
    unittest2.main()
