
import mock
import unittest2

import mitogen.core

import testlib

try:
    next
except NameError:
    def next(it):
        return it.next()


class IterSplitTest(unittest2.TestCase):
    func = staticmethod(mitogen.core.iter_split)

    def test_empty_buffer(self):
        lst = []
        trailer, cont = self.func(buf='', delim='\n', func=lst.append)
        self.assertTrue(cont)
        self.assertEquals('', trailer)
        self.assertEquals([], lst)

    def test_empty_line(self):
        lst = []
        trailer, cont = self.func(buf='\n', delim='\n', func=lst.append)
        self.assertTrue(cont)
        self.assertEquals('', trailer)
        self.assertEquals([''], lst)

    def test_one_line(self):
        buf = 'xxxx\n'
        lst = []
        trailer, cont = self.func(buf=buf, delim='\n', func=lst.append)
        self.assertTrue(cont)
        self.assertEquals('', trailer)
        self.assertEquals(lst, ['xxxx'])

    def test_one_incomplete(self):
        buf = 'xxxx\nyy'
        lst = []
        trailer, cont = self.func(buf=buf, delim='\n', func=lst.append)
        self.assertTrue(cont)
        self.assertEquals('yy', trailer)
        self.assertEquals(lst, ['xxxx'])

    def test_returns_false_immediately(self):
        buf = 'xxxx\nyy'
        func = lambda buf: False
        trailer, cont = self.func(buf=buf, delim='\n', func=func)
        self.assertFalse(cont)
        self.assertEquals('yy', trailer)

    def test_returns_false_second_call(self):
        buf = 'xxxx\nyy\nzz'
        it = iter([True, False])
        func = lambda buf: next(it)
        trailer, cont = self.func(buf=buf, delim='\n', func=func)
        self.assertFalse(cont)
        self.assertEquals('zz', trailer)


if __name__ == '__main__':
    unittest2.main()
