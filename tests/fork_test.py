import os
import random
import sys
import unittest

try:
    import _ssl
except ImportError:
    _ssl = None

try:
    import ssl
except ImportError:
    ssl = None

try:
    import ctypes
except ImportError:
    # Python 2.4
    ctypes = None

import mitogen

import testlib
import plain_old_module


def _find_ssl_linux():
    s = testlib.subprocess__check_output(['ldd', _ssl.__file__])
    for line in s.decode().splitlines():
        bits = line.split()
        if bits[0].startswith('libssl'):
            return bits[2]

def _find_ssl_darwin():
    s = testlib.subprocess__check_output(['otool', '-l', _ssl.__file__])
    for line in s.decode().splitlines():
        bits = line.split()
        if bits[0] == 'name' and 'libssl' in bits[1]:
            return bits[1]


if ctypes and sys.platform.startswith('linux'):
    LIBSSL_PATH = _find_ssl_linux()
elif ctypes and sys.platform == 'darwin':
    LIBSSL_PATH = _find_ssl_darwin()
else:
    LIBSSL_PATH = None

if ctypes and LIBSSL_PATH:
    c_ssl = ctypes.CDLL(LIBSSL_PATH)
    c_ssl.RAND_pseudo_bytes.argtypes = [ctypes.c_char_p, ctypes.c_int]
    c_ssl.RAND_pseudo_bytes.restype = ctypes.c_int


def ping():
    return 123


def random_random():
    return random.random()


def RAND_pseudo_bytes(n=32):
    buf = ctypes.create_string_buffer(n)
    assert 1 == c_ssl.RAND_pseudo_bytes(buf, n)
    return buf[:]


def exercise_importer(n):
    """
    Ensure the forked child has a sensible importer.
    """
    sys.path.remove(testlib.DATA_DIR)
    import simple_pkg.a
    return simple_pkg.a.subtract_one_add_two(n)


skipIfUnsupported = unittest.skipIf(
    condition=(not mitogen.fork.FORK_SUPPORTED),
    reason="mitogen.fork unsupported on this platform"
)


class ForkTest(testlib.RouterMixin, testlib.TestCase):
    def test_okay(self):
        context = self.router.fork()
        self.assertNotEqual(context.call(os.getpid), os.getpid())
        self.assertEqual(context.call(os.getppid), os.getpid())

    def test_random_module_diverges(self):
        context = self.router.fork()
        self.assertNotEqual(context.call(random_random), random_random())

    @unittest.skipIf(
        condition=LIBSSL_PATH is None or ctypes is None,
        reason='cant test libssl on this platform',
    )
    def test_ssl_module_diverges(self):
        # Ensure generator state is initialized.
        RAND_pseudo_bytes()
        context = self.router.fork()
        self.assertNotEqual(context.call(RAND_pseudo_bytes),
                            RAND_pseudo_bytes())

    def test_importer(self):
        context = self.router.fork()
        self.assertEqual(2, context.call(exercise_importer, 1))

    def test_on_start(self):
        recv = mitogen.core.Receiver(self.router)
        def on_start(econtext):
            sender = mitogen.core.Sender(econtext.parent, recv.handle)
            sender.send(123)
        context = self.router.fork(on_start=on_start)
        self.assertEqual(123, recv.get().unpickle())

ForkTest = skipIfUnsupported(ForkTest)


class DoubleChildTest(testlib.RouterMixin, testlib.TestCase):
    def test_okay(self):
        # When forking from the master process, Mitogen had nothing to do with
        # setting up stdio -- that was inherited wherever the Master is running
        # (supervisor, iTerm, etc). When forking from a Mitogen child context
        # however, Mitogen owns all of fd 0, 1, and 2, and during the fork
        # procedure, it deletes all of these descriptors. That leaves the
        # process in a weird state that must be handled by some combination of
        # fork.py and ExternalContext.main().

        # Below we simply test whether ExternalContext.main() managed to boot
        # successfully. In future, we need lots more tests.
        c1 = self.router.fork()
        c2 = self.router.fork(via=c1)
        self.assertEqual(123, c2.call(ping))

    def test_importer(self):
        c1 = self.router.fork(name='c1')
        c2 = self.router.fork(name='c2', via=c1)
        self.assertEqual(2, c2.call(exercise_importer, 1))

DoubleChildTest = skipIfUnsupported(DoubleChildTest)
