
import unittest2

import mitogen.core
import mitogen.error

import testlib


class MagicValueError(ValueError):
    pass


def func_throws_value_error(*args):
    raise ValueError(*args)


def func_throws_value_error_subclass(*args):
    raise MagicValueError(*args)


class MatchTest(testlib.RouterMixin, testlib.TestCase):
    def _test_no_match(self):
        context = self.router.fork()
        try:
           context.call(func_throws_value_error_subclass)
        except mitogen.error.match(ValueError):
            pass

    def test_no_match(self):
        self.assertRaises(mitogen.core.CallError,
            lambda: self._test_no_match())

    def test_builtin_match(self):
        context = self.router.fork()
        try:
            context.call(func_throws_value_error)
        except mitogen.error.match(ValueError):
            pass

    def test_direct_custom_match(self):
        context = self.router.fork()
        try:
           context.call(func_throws_value_error_subclass)
        except mitogen.error.match(MagicValueError):
            pass

    def test_indirect_match(self):
        context = self.router.fork()
        try:
           context.call(func_throws_value_error_subclass)
        except mitogen.error.match(ValueError):
            pass


if __name__ == '__main__':
    unittest2.main()
