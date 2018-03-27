
import ctypes
import os
import random
import ssl
import struct
import sys

import mitogen
import unittest2

import testlib
import plain_old_module


IS_64BIT = struct.calcsize('P') == 8
PLATFORM_TO_PATH = {
    ('darwin', False): '/usr/lib/libssl.dylib',
    ('darwin', True): '/usr/lib/libssl.dylib',
    ('linux2', False): '/usr/lib/libssl.so',
    ('linux2', True): '/usr/lib/x86_64-linux-gnu/libssl.so',
}

c_ssl = ctypes.CDLL(PLATFORM_TO_PATH[sys.platform, IS_64BIT])
c_ssl.RAND_pseudo_bytes.argtypes = [ctypes.c_char_p, ctypes.c_int]
c_ssl.RAND_pseudo_bytes.restype = ctypes.c_int


def random_random():
    return random.random()


def RAND_pseudo_bytes(n=32):
    buf = ctypes.create_string_buffer(n)
    assert 1 == c_ssl.RAND_pseudo_bytes(buf, n)
    return buf[:]


class ForkTest(testlib.RouterMixin, unittest2.TestCase):
    def test_okay(self):
        context = self.router.fork()
        self.assertNotEqual(context.call(os.getpid), os.getpid())
        self.assertEqual(context.call(os.getppid), os.getpid())

    def test_random_module_diverges(self):
        context = self.router.fork()
        self.assertNotEqual(context.call(random_random), random_random())

    def test_ssl_module_diverges(self):
        # Ensure generator state is initialized.
        RAND_pseudo_bytes()
        context = self.router.fork()
        self.assertNotEqual(context.call(RAND_pseudo_bytes),
                            RAND_pseudo_bytes())


if __name__ == '__main__':
    unittest2.main()
