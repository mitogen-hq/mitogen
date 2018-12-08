
from __future__ import absolute_import
import os.path
import subprocess
import tempfile
import unittest2

import mock

import ansible_mitogen.connection
import testlib


LOGGER_NAME = ansible_mitogen.target.LOG.name


class OptionalIntTest(unittest2.TestCase):
    func = staticmethod(ansible_mitogen.connection.optional_int)

    def test_already_int(self):
        self.assertEquals(0, self.func(0))
        self.assertEquals(1, self.func(1))
        self.assertEquals(-1, self.func(-1))

    def test_is_string(self):
        self.assertEquals(0, self.func("0"))
        self.assertEquals(1, self.func("1"))
        self.assertEquals(-1, self.func("-1"))

    def test_is_none(self):
        self.assertEquals(None, self.func(None))

    def test_is_junk(self):
        self.assertEquals(None, self.func({1:2}))


if __name__ == '__main__':
    unittest2.main()
