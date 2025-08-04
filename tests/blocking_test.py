import os
import tempfile

import mitogen.core

import testlib

class BlockingIOTest(testlib.TestCase):
    def setUp(self):
        super(BlockingIOTest, self).setUp()
        self.fp = tempfile.TemporaryFile()
        self.fd = self.fp.fileno()

    def tearDown(self):
        self.fp.close()
        super(BlockingIOTest, self).tearDown()

    def test_get_blocking(self):
        if hasattr(os, 'get_blocking'):
            self.assertEqual(
                os.get_blocking(self.fd), mitogen.core.get_blocking(self.fd),
            )
        self.assertTrue(mitogen.core.get_blocking(self.fd) is True)

    def test_set_blocking(self):
        mitogen.core.set_blocking(self.fd, False)
        if hasattr(os, 'get_blocking'):
            self.assertEqual(
                os.get_blocking(self.fd), mitogen.core.get_blocking(self.fd),
            )
        self.assertTrue(mitogen.core.get_blocking(self.fd) is False)

