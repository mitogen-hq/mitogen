
import os
import unittest

import mitogen
import mitogen.ssh
import mitogen.utils

import testlib
import plain_old_module


class LocalTest(testlib.RouterMixin, unittest.TestCase):
    stream_class = mitogen.ssh.Stream

    def test_stream_name(self):
        context = self.router.local()
        pid = context.call(os.getpid)
        self.assertEquals('local.%d' % (pid,), context.name)


if __name__ == '__main__':
    unittest.main()
