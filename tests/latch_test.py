
import unittest2

import mitogen.core

import testlib


class EmptyTest(testlib.TestCase):
    klass = mitogen.core.Latch

    def test_is_empty(self):
        latch = self.klass()
        self.assertTrue(latch.empty())

    def test_is_nonempty(self):
        latch = self.klass()
        latch.put(None)
        self.assertTrue(not latch.empty())


class GetTest(testlib.TestCase):
    klass = mitogen.core.Latch
    # TODO: test multiple waiters.

    def test_empty_noblock(self):
        latch = self.klass()
        exc = self.assertRaises(mitogen.core.TimeoutError,
            lambda: latch.get(block=False))

    def test_empty_zero_timeout(self):
        latch = self.klass()
        exc = self.assertRaises(mitogen.core.TimeoutError,
            lambda: latch.get(timeout=0))

    def test_nonempty(self):
        obj = object()
        latch = self.klass()
        latch.put(obj)
        self.assertEquals(obj, latch.get())

    def test_nonempty_noblock(self):
        obj = object()
        latch = self.klass()
        latch.put(obj)
        self.assertEquals(obj, latch.get(block=False))

    def test_nonempty_zero_timeout(self):
        obj = object()
        latch = self.klass()
        latch.put(obj)
        self.assertEquals(obj, latch.get(timeout=0))


class PutTest(testlib.TestCase):
    klass = mitogen.core.Latch

    def test_put(self):
        latch = self.klass()
        latch.put(None)
        self.assertEquals(None, latch.get())


if __name__ == '__main__':
    unittest2.main()
