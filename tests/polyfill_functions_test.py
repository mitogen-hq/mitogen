import testlib

import mitogen.core
from mitogen.core import b


class BytesPartitionTest(testlib.TestCase):
    func = staticmethod(mitogen.core.bytes_partition)

    def test_no_sep(self):
        left, sep, right = self.func(b('dave'), b('x'))
        self.assertTrue(isinstance(left, mitogen.core.BytesType))
        self.assertTrue(isinstance(sep, mitogen.core.BytesType))
        self.assertTrue(isinstance(right, mitogen.core.BytesType))
        self.assertEqual(left, b('dave'))
        self.assertEqual(sep, b(''))
        self.assertEqual(right, b(''))

    def test_one_sep(self):
        left, sep, right = self.func(b('davexdave'), b('x'))
        self.assertTrue(isinstance(left, mitogen.core.BytesType))
        self.assertTrue(isinstance(sep, mitogen.core.BytesType))
        self.assertTrue(isinstance(right, mitogen.core.BytesType))
        self.assertEqual(left, b('dave'))
        self.assertEqual(sep, b('x'))
        self.assertEqual(right, b('dave'))

    def test_two_seps(self):
        left, sep, right = self.func(b('davexdavexdave'), b('x'))
        self.assertTrue(isinstance(left, mitogen.core.BytesType))
        self.assertTrue(isinstance(sep, mitogen.core.BytesType))
        self.assertTrue(isinstance(right, mitogen.core.BytesType))
        self.assertEqual(left, b('dave'))
        self.assertEqual(sep, b('x'))
        self.assertEqual(right, b('davexdave'))


class StrPartitionTest(testlib.TestCase):
    func = staticmethod(mitogen.core.str_partition)

    def test_no_sep(self):
        left, sep, right = self.func(u'dave', u'x')
        self.assertTrue(isinstance(left, mitogen.core.UnicodeType))
        self.assertTrue(isinstance(sep, mitogen.core.UnicodeType))
        self.assertTrue(isinstance(right, mitogen.core.UnicodeType))
        self.assertEqual(left, u'dave')
        self.assertEqual(sep, u'')
        self.assertEqual(right, u'')

    def test_one_sep(self):
        left, sep, right = self.func(u'davexdave', u'x')
        self.assertTrue(isinstance(left, mitogen.core.UnicodeType))
        self.assertTrue(isinstance(sep, mitogen.core.UnicodeType))
        self.assertTrue(isinstance(right, mitogen.core.UnicodeType))
        self.assertEqual(left, u'dave')
        self.assertEqual(sep, u'x')
        self.assertEqual(right, u'dave')

    def test_two_seps(self):
        left, sep, right = self.func(u'davexdavexdave', u'x')
        self.assertTrue(isinstance(left, mitogen.core.UnicodeType))
        self.assertTrue(isinstance(sep, mitogen.core.UnicodeType))
        self.assertTrue(isinstance(right, mitogen.core.UnicodeType))
        self.assertEqual(left, u'dave')
        self.assertEqual(sep, u'x')
        self.assertEqual(right, u'davexdave')


class StrRpartitionTest(testlib.TestCase):
    func = staticmethod(mitogen.core.str_rpartition)

    def test_no_sep(self):
        left, sep, right = self.func(u'dave', u'x')
        self.assertTrue(isinstance(left, mitogen.core.UnicodeType))
        self.assertTrue(isinstance(sep, mitogen.core.UnicodeType))
        self.assertTrue(isinstance(right, mitogen.core.UnicodeType))
        self.assertEqual(left, u'')
        self.assertEqual(sep, u'')
        self.assertEqual(right, u'dave')

    def test_one_sep(self):
        left, sep, right = self.func(u'davexdave', u'x')
        self.assertTrue(isinstance(left, mitogen.core.UnicodeType))
        self.assertTrue(isinstance(sep, mitogen.core.UnicodeType))
        self.assertTrue(isinstance(right, mitogen.core.UnicodeType))
        self.assertEqual(left, u'dave')
        self.assertEqual(sep, u'x')
        self.assertEqual(right, u'dave')

    def test_two_seps(self):
        left, sep, right = self.func(u'davexdavexdave', u'x')
        self.assertTrue(isinstance(left, mitogen.core.UnicodeType))
        self.assertTrue(isinstance(sep, mitogen.core.UnicodeType))
        self.assertTrue(isinstance(right, mitogen.core.UnicodeType))
        self.assertEqual(left, u'davexdave')
        self.assertEqual(sep, u'x')
        self.assertEqual(right, u'dave')
