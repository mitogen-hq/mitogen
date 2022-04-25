import sys

try:
    from io import StringIO
    from io import BytesIO
except ImportError:
    from StringIO import StringIO as StringIO
    from StringIO import StringIO as BytesIO

import unittest

import mitogen.core
from mitogen.core import b

import testlib


####
#### see also message_test.py / PickledTest
####


class BlobTest(testlib.TestCase):
    klass = mitogen.core.Blob

    def make(self):
        return self.klass(b('x') * 128)

    def test_repr(self):
        blob = self.make()
        self.assertEqual('[blob: 128 bytes]', repr(blob))

    def test_decays_on_constructor(self):
        blob = self.make()
        self.assertEqual(b('x') * 128, mitogen.core.BytesType(blob))

    def test_decays_on_write(self):
        blob = self.make()
        io = BytesIO()
        io.write(blob)
        self.assertEqual(128, io.tell())
        self.assertEqual(b('x') * 128, io.getvalue())

    def test_message_roundtrip(self):
        blob = self.make()
        msg = mitogen.core.Message.pickled(blob)
        blob2 = msg.unpickle()
        self.assertEqual(type(blob), type(blob2))
        self.assertEqual(repr(blob), repr(blob2))
        self.assertEqual(mitogen.core.BytesType(blob),
                          mitogen.core.BytesType(blob2))


class SecretTest(testlib.TestCase):
    klass = mitogen.core.Secret

    def make(self):
        return self.klass('password')

    def test_repr(self):
        secret = self.make()
        self.assertEqual('[secret]', repr(secret))

    def test_decays_on_constructor(self):
        secret = self.make()
        self.assertEqual('password', mitogen.core.UnicodeType(secret))

    def test_decays_on_write(self):
        secret = self.make()
        io = StringIO()
        io.write(secret)
        self.assertEqual(8, io.tell())
        self.assertEqual('password', io.getvalue())

    def test_message_roundtrip(self):
        secret = self.make()
        msg = mitogen.core.Message.pickled(secret)
        secret2 = msg.unpickle()
        self.assertEqual(type(secret), type(secret2))
        self.assertEqual(repr(secret), repr(secret2))
        self.assertEqual(mitogen.core.b(secret),
                          mitogen.core.b(secret2))


class KwargsTest(testlib.TestCase):
    klass = mitogen.core.Kwargs

    def test_empty(self):
        kw = self.klass({})
        self.assertEqual({}, kw)
        self.assertEqual('Kwargs({})', repr(kw))
        klass, (dct,) = kw.__reduce__()
        self.assertTrue(klass is self.klass)
        self.assertTrue(type(dct) is dict)
        self.assertEqual({}, dct)

    @unittest.skipIf(condition=(sys.version_info >= (2, 6)),
                      reason='py<2.6 only')
    def test_bytes_conversion(self):
        kw = self.klass({u'key': 123})
        self.assertEqual({'key': 123}, kw)
        self.assertEqual("Kwargs({'key': 123})", repr(kw))

    @unittest.skipIf(condition=not mitogen.core.PY3,
                      reason='py3 only')
    def test_unicode_conversion(self):
        kw = self.klass({mitogen.core.b('key'): 123})
        self.assertEqual({u'key': 123}, kw)
        self.assertEqual("Kwargs({'key': 123})", repr(kw))
        klass, (dct,) = kw.__reduce__()
        self.assertTrue(klass is self.klass)
        self.assertTrue(type(dct) is dict)
        self.assertEqual({u'key': 123}, dct)
        key, = dct
        self.assertTrue(type(key) is mitogen.core.UnicodeType)


class AdornedUnicode(mitogen.core.UnicodeType):
    pass


class ToTextTest(testlib.TestCase):
    func = staticmethod(mitogen.core.to_text)

    def test_bytes(self):
        s = self.func(mitogen.core.b('bytes'))
        self.assertEqual(mitogen.core.UnicodeType, type(s))
        self.assertEqual(s, u'bytes')

    def test_unicode(self):
        s = self.func(u'text')
        self.assertEqual(mitogen.core.UnicodeType, type(s))
        self.assertEqual(s, u'text')

    def test_adorned_unicode(self):
        s = self.func(AdornedUnicode(u'text'))
        self.assertEqual(mitogen.core.UnicodeType, type(s))
        self.assertEqual(s, u'text')

    def test_integer(self):
        s = self.func(123)
        self.assertEqual(mitogen.core.UnicodeType, type(s))
        self.assertEqual(s, u'123')
