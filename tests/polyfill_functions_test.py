
import testlib
import unittest2

import mitogen.core
from mitogen.core import b


class BytesPartitionTest(testlib.TestCase):
    func = staticmethod(mitogen.core.bytes_partition)

    def test_no_sep(self):
        left, sep, right = self.func(b('dave'), b('x'))
        self.assertTrue(isinstance(left, mitogen.core.BytesType))
        self.assertTrue(isinstance(sep, mitogen.core.BytesType))
        self.assertTrue(isinstance(right, mitogen.core.BytesType))
        self.assertEquals(left, b('dave'))
        self.assertEquals(sep, b(''))
        self.assertEquals(right, b(''))

    def test_one_sep(self):
        left, sep, right = self.func(b('davexdave'), b('x'))
        self.assertTrue(isinstance(left, mitogen.core.BytesType))
        self.assertTrue(isinstance(sep, mitogen.core.BytesType))
        self.assertTrue(isinstance(right, mitogen.core.BytesType))
        self.assertEquals(left, b('dave'))
        self.assertEquals(sep, b('x'))
        self.assertEquals(right, b('dave'))

    def test_two_seps(self):
        left, sep, right = self.func(b('davexdavexdave'), b('x'))
        self.assertTrue(isinstance(left, mitogen.core.BytesType))
        self.assertTrue(isinstance(sep, mitogen.core.BytesType))
        self.assertTrue(isinstance(right, mitogen.core.BytesType))
        self.assertEquals(left, b('dave'))
        self.assertEquals(sep, b('x'))
        self.assertEquals(right, b('davexdave'))


class StrPartitionTest(testlib.TestCase):
    func = staticmethod(mitogen.core.str_partition)

    def test_no_sep(self):
        left, sep, right = self.func(u'dave', u'x')
        self.assertTrue(isinstance(left, mitogen.core.UnicodeType))
        self.assertTrue(isinstance(sep, mitogen.core.UnicodeType))
        self.assertTrue(isinstance(right, mitogen.core.UnicodeType))
        self.assertEquals(left, u'dave')
        self.assertEquals(sep, u'')
        self.assertEquals(right, u'')

    def test_one_sep(self):
        left, sep, right = self.func(u'davexdave', u'x')
        self.assertTrue(isinstance(left, mitogen.core.UnicodeType))
        self.assertTrue(isinstance(sep, mitogen.core.UnicodeType))
        self.assertTrue(isinstance(right, mitogen.core.UnicodeType))
        self.assertEquals(left, u'dave')
        self.assertEquals(sep, u'x')
        self.assertEquals(right, u'dave')

    def test_two_seps(self):
        left, sep, right = self.func(u'davexdavexdave', u'x')
        self.assertTrue(isinstance(left, mitogen.core.UnicodeType))
        self.assertTrue(isinstance(sep, mitogen.core.UnicodeType))
        self.assertTrue(isinstance(right, mitogen.core.UnicodeType))
        self.assertEquals(left, u'dave')
        self.assertEquals(sep, u'x')
        self.assertEquals(right, u'davexdave')


class StrRpartitionTest(testlib.TestCase):
    func = staticmethod(mitogen.core.str_rpartition)

    def test_no_sep(self):
        left, sep, right = self.func(u'dave', u'x')
        self.assertTrue(isinstance(left, mitogen.core.UnicodeType))
        self.assertTrue(isinstance(sep, mitogen.core.UnicodeType))
        self.assertTrue(isinstance(right, mitogen.core.UnicodeType))
        self.assertEquals(left, u'')
        self.assertEquals(sep, u'')
        self.assertEquals(right, u'dave')

    def test_one_sep(self):
        left, sep, right = self.func(u'davexdave', u'x')
        self.assertTrue(isinstance(left, mitogen.core.UnicodeType))
        self.assertTrue(isinstance(sep, mitogen.core.UnicodeType))
        self.assertTrue(isinstance(right, mitogen.core.UnicodeType))
        self.assertEquals(left, u'dave')
        self.assertEquals(sep, u'x')
        self.assertEquals(right, u'dave')

    def test_two_seps(self):
        left, sep, right = self.func(u'davexdavexdave', u'x')
        self.assertTrue(isinstance(left, mitogen.core.UnicodeType))
        self.assertTrue(isinstance(sep, mitogen.core.UnicodeType))
        self.assertTrue(isinstance(right, mitogen.core.UnicodeType))
        self.assertEquals(left, u'davexdave')
        self.assertEquals(sep, u'x')
        self.assertEquals(right, u'dave')


if __name__ == '__main__':
    unittest2.main()
