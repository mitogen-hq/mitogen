import pickle
import sys

import mitogen.core

import testlib
import testmod_toplevel


class ConstructorTest(testlib.TestCase):
    klass = mitogen.core.CallError

    def test_string_noargs(self):
        e = self.klass('%s%s')
        self.assertEqual(e.args[0], '%s%s')
        self.assertIsInstance(e.args[0], mitogen.core.UnicodeType)

    def test_string_args(self):
        e = self.klass('%s%s', 1, 1)
        self.assertEqual(e.args[0], '11')
        self.assertIsInstance(e.args[0], mitogen.core.UnicodeType)

    def test_from_exc(self):
        ve = testmod_toplevel.MyError('eek')
        e = self.klass(ve)
        self.assertEqual(e.args[0], 'testmod_toplevel.MyError: eek')
        self.assertIsInstance(e.args[0], mitogen.core.UnicodeType)

    def test_form_base_exc(self):
        ve = SystemExit('eek')
        e = self.klass(ve)
        cls = ve.__class__
        self.assertEqual(e.args[0],
            # varies across 2/3.
            '%s.%s: eek' % (cls.__module__, cls.__name__))
        self.assertIsInstance(e.args[0], mitogen.core.UnicodeType)

    def test_from_exc_tb(self):
        try:
            raise testmod_toplevel.MyError('eek')
        except testmod_toplevel.MyError:
            ve = sys.exc_info()[1]
            e = self.klass(ve)

        self.assertTrue(e.args[0].startswith('testmod_toplevel.MyError: eek'))
        self.assertIsInstance(e.args[0], mitogen.core.UnicodeType)
        self.assertIn('test_from_exc_tb', e.args[0])

    def test_bytestring_conversion(self):
        e = self.klass(mitogen.core.b('bytes'))
        self.assertEqual(u'bytes', e.args[0])
        self.assertIsInstance(e.args[0], mitogen.core.UnicodeType)

    def test_reduce(self):
        e = self.klass('eek')
        func, (arg,) = e.__reduce__()
        self.assertIs(func, mitogen.core._unpickle_call_error)
        self.assertEqual(arg, e.args[0])


class UnpickleCallErrorTest(testlib.TestCase):
    func = staticmethod(mitogen.core._unpickle_call_error)

    def test_not_unicode(self):
        self.assertRaises(TypeError,
            lambda: self.func(mitogen.core.b('bad')))

    def test_oversized(self):
        self.assertRaises(TypeError,
            lambda: self.func(mitogen.core.b('b'*10001)))

    def test_reify(self):
        e = self.func(u'some error')
        self.assertEqual(mitogen.core.CallError, e.__class__)
        self.assertEqual(1, len(e.args))
        self.assertEqual(mitogen.core.UnicodeType, type(e.args[0]))
        self.assertEqual(u'some error', e.args[0])


class PickleTest(testlib.TestCase):
    klass = mitogen.core.CallError

    def test_string_noargs(self):
        e = self.klass('%s%s')
        e2 = pickle.loads(pickle.dumps(e))
        self.assertEqual(e2.args[0], '%s%s')

    def test_string_args(self):
        e = self.klass('%s%s', 1, 1)
        e2 = pickle.loads(pickle.dumps(e))
        self.assertEqual(e2.args[0], '11')

    def test_from_exc(self):
        ve = testmod_toplevel.MyError('eek')
        e = self.klass(ve)
        e2 = pickle.loads(pickle.dumps(e))
        self.assertEqual(e2.args[0], 'testmod_toplevel.MyError: eek')

    def test_from_exc_tb(self):
        try:
            raise testmod_toplevel.MyError('eek')
        except testmod_toplevel.MyError:
            ve = sys.exc_info()[1]
            e = self.klass(ve)

        e2 = pickle.loads(pickle.dumps(e))
        self.assertTrue(e2.args[0].startswith('testmod_toplevel.MyError: eek'))
        self.assertIn('test_from_exc_tb', e2.args[0])
