import testlib
import mitogen.core


class ConstructorTest(testlib.TestCase):
    klass = mitogen.core.Error

    def test_literal_no_format(self):
        e = self.klass('error')
        self.assertEqual(e.args[0], 'error')
        self.assertTrue(isinstance(e.args[0], mitogen.core.UnicodeType))

    def test_literal_format_chars_present(self):
        e = self.klass('error%s')
        self.assertEqual(e.args[0], 'error%s')
        self.assertTrue(isinstance(e.args[0], mitogen.core.UnicodeType))

    def test_format(self):
        e = self.klass('error%s', 123)
        self.assertEqual(e.args[0], 'error123')
        self.assertTrue(isinstance(e.args[0], mitogen.core.UnicodeType))

    def test_bytes_to_unicode(self):
        e = self.klass(mitogen.core.b('error'))
        self.assertEqual(e.args[0], 'error')
        self.assertTrue(isinstance(e.args[0], mitogen.core.UnicodeType))
