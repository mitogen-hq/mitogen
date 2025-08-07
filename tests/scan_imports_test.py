import sys
import textwrap
import unittest

from mitogen.imports import scan_imports

import testlib


class EmptyTest(testlib.TestCase):
    def test_empty(self):
        self.assertEqual(list(scan_imports('')), [])


class DefaultsTest(testlib.TestCase):
    SOURCE = textwrap.dedent("""\
        import a; import b.c as d
        from e import *; from f import g, h as j
        """)

    @unittest.skipIf(sys.version_info < (3, 0), "Py 2.x, default relative imports")
    def test_default_absolute(self):
        self.assertEqual(
            list(scan_imports(self.SOURCE)),
            [(0, 'a', ()), (0, 'b.c', ()),
             (0, 'e', ('*',)), (0, 'f', ('g', 'h'))],
        )

    @unittest.skipIf(sys.version_info >= (3, 0), "Py 3.x, default absolute imports")
    def test_default_relative(self):
        self.assertEqual(
            list(scan_imports(self.SOURCE)),
            [(-1, 'a', ()), (-1, 'b.c', ()),
             (-1, 'e', ('*',)), (-1, 'f', ('g', 'h'))],
        )


class ExplicitAbsoluteTest(testlib.TestCase):
    SOURCE = textwrap.dedent("""\
        from __future__ import absolute_import
        import a; import b.c as d
        from e import *; from f import g, h as j
        """)

    @unittest.skipIf(sys.version_info < (2, 5), "Py < 2.5, no absolute_import")
    def test_explicit_absolute(self):
        self.assertEqual(
            list(scan_imports(self.SOURCE)),
            [(0, '__future__', ('absolute_import',)),
             (0, 'a', ()), (0, 'b.c', ()),
             (0, 'e', ('*',)), (0, 'f', ('g', 'h'))],
        )


class ExplicitRelativeTest(testlib.TestCase):
    SOURCE = textwrap.dedent("""\
        from . import a
        from .a import b
        from .. import c
        from ..d.e import f as g, h
        from ... import *
        """)

    @unittest.skipIf(sys.version_info < (2, 5), "Py < 2.5, no explicit relative")
    def test_explicit_relative(self):
        self.assertEqual(
            list(scan_imports(self.SOURCE)),
            [(1, '', ('a',)), (1, 'a', ('b',)), (2, '', ('c',)),
             (2, 'd.e', ('f', 'g')), (3, '', ('*',))],
        )


class ClassBodyTest(testlib.TestCase):
    SOURCE = textwrap.dedent("""\
        def foo(a, b):
            import c
            from d import e as f

        def bar():
            import g
            from h import *
        """)

    def test_in_class(self):
        self.assertEqual(
            [(mod, names) for _, mod, names in scan_imports(self.SOURCE)],
            [('c', ()), ('d', ('e',)), ('g', ()), ('h', ('*',))],
        )


class FunctionBodyTest(testlib.TestCase):
    SOURCE = textwrap.dedent("""\
        class Foo(object):
            a = b
            import c
            from d import e as f

        def Bar:
            import g
            from h import *
        """)

    def test_in_func(self):
        self.assertEqual(
            [(mod, names) for _, mod, names in scan_imports(self.SOURCE)],
            [('c', ()), ('d', ('e',)), ('g', ()), ('h', ('*',))],
        )
