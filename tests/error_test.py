
import unittest2

import testlib
import mitogen.core


class ConstructorTest(testlib.TestCase):
    klass = mitogen.core.Error

    def test_literal_no_format(self):
        e = self.klass('error')
        self.assertEquals(e.args[0], 'error')
        self.assertTrue(isinstance(e.args[0], mitogen.core.UnicodeType))

    def test_literal_format_chars_present(self):
        e = self.klass('error%s')
        self.assertEquals(e.args[0], 'error%s')
        self.assertTrue(isinstance(e.args[0], mitogen.core.UnicodeType))

    def test_format(self):
        e = self.klass('error%s', 123)
        self.assertEquals(e.args[0], 'error123')
        self.assertTrue(isinstance(e.args[0], mitogen.core.UnicodeType))

    def test_bytes_to_unicode(self):
        e = self.klass(mitogen.core.b('error'))
        self.assertEquals(e.args[0], 'error')
        self.assertTrue(isinstance(e.args[0], mitogen.core.UnicodeType))


if __name__ == '__main__':
    unittest2.main()
