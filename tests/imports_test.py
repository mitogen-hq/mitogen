import os
import sys
import unittest

import mitogen.imports

import testlib


def testmod_compile(path):
    path = os.path.join(testlib.MODS_DIR, path)
    f = open(path, 'rb')
    co = compile(f.read(), path, 'exec')
    f.close()
    return co


class ScanCodeImportsTest(testlib.TestCase):
    func = staticmethod(mitogen.imports.codeobj_imports)

    @unittest.skipIf(sys.version_info < (3, 0), "Py is 2.x, would be relative")
    def test_default_absolute(self):
        co = testmod_compile('scanning/defaults.py')
        expected = [
            (0, 'a', ()), (0, 'a.b', ()), (0, 'c', ()),
            (0, 'e', ()), (0, 'e.f', ()), (0, 'h', ()),
            (0, 'i', ()),
            (0, 'j', ('k', 'l', 'm')),
            (0, 'o', ('*',)),
        ]
        self.assertEqual(list(self.func(co)), expected)

    @unittest.skipIf(sys.version_info >= (3, 0), "Py is 3.x, would be absolute")
    def test_default_relative(self):
        co = testmod_compile('scanning/defaults.py')
        expected = [
            (-1, 'a', ()), (-1, 'a.b', ()), (-1, 'c', ()),
            (-1, 'e', ()), (-1, 'e.f', ()), (-1, 'h', ()),
            (-1, 'i', ()),
            (-1, 'j', ('k', 'l', 'm')),
            (-1, 'o', ('*',)),
        ]
        self.assertEqual(list(self.func(co)), expected)

    @unittest.skipIf(sys.version_info < (2, 5), "Py is 2.4, no absolute_import")
    def test_explicit_absolute(self):
        co = testmod_compile('scanning/has_absolute_import.py')
        expected = [
            (0, '__future__', ('absolute_import',)),

            (0, 'a', ()), (0, 'a.b', ()), (0, 'c', ()),
            (0, 'e', ()), (0, 'e.f', ()), (0, 'h', ()),
            (0, 'i', ()),
            (0, 'j', ('k', 'l', 'm')),
            (0, 'o', ('*',)),
        ]
        self.assertEqual(list(self.func(co)), expected)

    @unittest.skipIf(sys.version_info < (2, 5), "Py is 2.4, no `from . import x`")
    def test_explicit_relative(self):
        co = testmod_compile('scanning/explicit_relative.py')
        expected = [
            (1, '', ('a',)),
            (1, 'b', ('c', 'd')),
            (3, '', ('f', 'j')),
        ]
        self.assertEqual(list(self.func(co)), expected)

    def test_scoped_class(self):
        # Imports in `class` or `def` are ignored, a bad heuristc to detect
        # lazy imports and skip sending the pre-emptively.
        # See
        # - https://github.com/mitogen-hq/mitogen/issues/682
        # - https://github.com/mitogen-hq/mitogen/issues/1325#issuecomment-3170482014
        co = testmod_compile('scanning/scoped_class.py')
        self.assertEqual(list(self.func(co)), [])

        pass

    def test_scoped_function(self):
        co = testmod_compile('scanning/scoped_function.py')
        self.assertEqual(list(self.func(co)), [])

    @unittest.skipIf(sys.version_info >= (3, 0), "Python is 3.x, which prunes")
    def test_scoped_if_else_unpruned(self):
        co = testmod_compile('scanning/scoped_if_else.py')
        level = (-1, 0)[int(sys.version_info >= (3, 0))]
        expected = [
            (level, 'sys', ()),
            (level, 'in_if_always_true', ()),
            (level, 'in_if_always_true', ('x', 'z')),
            # Python 2.x does no pruning
            (level, 'in_else_never_true', ()),
            (level, 'in_else_never_true', ('x', 'z')),
            (level, 'in_if_py3', ()),
            (level, 'in_if_py3', ('x', 'z')),
            (level, 'in_else_py2', ()),
            (level, 'in_else_py2', ('x', 'z')),
        ]
        self.assertEqual(list(self.func(co)), expected)

    @unittest.skipIf(sys.version_info < (3, 0), "Python is 2.x, which doesn't prune")
    def test_scoped_if_else_pruned(self):
        co = testmod_compile('scanning/scoped_if_else.py')
        level = (-1, 0)[int(sys.version_info >= (3, 0))]
        expected = [
            (level, 'sys', ()),
            (level, 'in_if_always_true', ()),
            (level, 'in_if_always_true', ('x', 'z')),
            # Python 3.x prunes some impossible branches ...
            (level, 'in_if_py3', ()),
            (level, 'in_if_py3', ('x', 'z')),
            # ... but not sys.version_info ones
            (level, 'in_else_py2', ()),
            (level, 'in_else_py2', ('x', 'z')),
        ]
        self.assertEqual(list(self.func(co)), expected)

    def test_scoped_try_except(self):
        co = testmod_compile('scanning/scoped_try_except.py')
        level = (-1, 0)[int(sys.version_info >= (3, 0))]
        expected = [
            (level, 'in_try', ()),
            (level, 'in_try', ('x', 'z')),
            (level, 'in_except_importerror', ()),
            (level, 'in_except_importerror', ('x', 'z')),
            (level, 'in_except_exception', ()),
            (level, 'in_except_exception', ('x', 'z')),
        ]
        self.assertEqual(list(self.func(co)), expected)
