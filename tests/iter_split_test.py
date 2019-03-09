
import mock
import unittest2

import mitogen.core

import testlib


class IterSplitTest(unittest2.TestCase):
    func = staticmethod(mitogen.core.iter_split)

    def test_empty_buffer(self):
        lst = []
        trailer = self.func(buf='', delim='\n', func=lst.append)
        self.assertEquals('', trailer)
        self.assertEquals([], lst)

    def test_empty_line(self):
        lst = []
        trailer = self.func(buf='\n', delim='\n', func=lst.append)
        self.assertEquals('', trailer)
        self.assertEquals([''], lst)

    def test_one_line(self):
        buf = 'xxxx\n'
        lst = []
        trailer = self.func(buf=buf, delim='\n', func=lst.append)
        self.assertEquals('', trailer)
        self.assertEquals(lst, ['xxxx'])

    def test_one_incomplete(self):
        buf = 'xxxx\nyy'
        lst = []
        trailer = self.func(buf=buf, delim='\n', func=lst.append)
        self.assertEquals('yy', trailer)
        self.assertEquals(lst, ['xxxx'])


if __name__ == '__main__':
    unittest2.main()
