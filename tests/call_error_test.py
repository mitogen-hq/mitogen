import os
import pickle

import unittest2

import mitogen.core


class ConstructorTest(unittest2.TestCase):
    klass = mitogen.core.CallError

    def test_string_noargs(self):
        e = self.klass('%s%s')
        self.assertEquals(e[0], '%s%s')

    def test_string_args(self):
        e = self.klass('%s%s', 1, 1)
        self.assertEquals(e[0], '11')

    def test_from_exc(self):
        ve = ValueError('eek')
        e = self.klass(ve)
        self.assertEquals(e[0], 'exceptions.ValueError: eek')

    def test_form_base_exc(self):
        ve = SystemExit('eek')
        e = self.klass(ve)
        self.assertEquals(e[0], 'exceptions.SystemExit: eek')

    def test_from_exc_tb(self):
        try:
            raise ValueError('eek')
        except ValueError, ve:
            e = self.klass(ve)

        self.assertTrue(e[0].startswith('exceptions.ValueError: eek'))
        self.assertTrue('test_from_exc_tb' in e[0])


class PickleTest(unittest2.TestCase):
    klass = mitogen.core.CallError

    def test_string_noargs(self):
        e = self.klass('%s%s')
        e2 = pickle.loads(pickle.dumps(e))
        self.assertEquals(e2[0], '%s%s')

    def test_string_args(self):
        e = self.klass('%s%s', 1, 1)
        e2 = pickle.loads(pickle.dumps(e))
        self.assertEquals(e2[0], '11')

    def test_from_exc(self):
        ve = ValueError('eek')
        e = self.klass(ve)
        e2 = pickle.loads(pickle.dumps(e))
        self.assertEquals(e2[0], 'exceptions.ValueError: eek')

    def test_from_exc_tb(self):
        try:
            raise ValueError('eek')
        except ValueError, ve:
            e = self.klass(ve)

        e2 = pickle.loads(pickle.dumps(e))
        self.assertTrue(e2[0].startswith('exceptions.ValueError: eek'))
        self.assertTrue('test_from_exc_tb' in e2[0])


if __name__ == '__main__':
    unittest2.main()
