import os.path
import sys
import textwrap
import unittest

import ansible_mitogen.module_finder

import testlib


class ScanFromListTest(testlib.TestCase):
    def test_absolute_imports(self):
        source = textwrap.dedent('''\
            from __future__ import absolute_import
            import a; import b.c; from d.e import f; from g import h, i
        ''')
        code = compile(source, '<str>', 'exec')
        self.assertEqual(
            list(ansible_mitogen.module_finder.scan_fromlist(code)),
            [(0, '__future__.absolute_import'), (0, 'a'), (0, 'b.c'), (0, 'd.e.f'), (0, 'g.h'), (0, 'g.i')],
        )


class WalkImportsTest(testlib.TestCase):
    def test_absolute_imports(self):
        source = textwrap.dedent('''\
            from __future__ import absolute_import
            import a; import b; import b.c; from b.d import e, f
        ''')
        code = compile(source, '<str>', 'exec')

        self.assertEqual(
            list(ansible_mitogen.module_finder.walk_imports(code)),
            ['__future__', '__future__.absolute_import', 'a', 'b', 'b', 'b.c', 'b', 'b.d', 'b.d.e', 'b.d.f'],
        )
        self.assertEqual(
            list(ansible_mitogen.module_finder.walk_imports(code, prefix='b')),
            ['b.c', 'b.d', 'b.d.e', 'b.d.f'],
        )


class ScanTest(testlib.TestCase):
    module_name = 'ansible_module_module_finder_test__this_should_not_matter'
    module_path = os.path.join(testlib.ANSIBLE_MODULES_DIR, 'module_finder_test.py')
    search_path = (
        'does_not_exist/module_utils',
        testlib.ANSIBLE_MODULE_UTILS_DIR,
    )

    @staticmethod
    def relpath(path):
        return os.path.relpath(path, testlib.ANSIBLE_MODULE_UTILS_DIR)

    @unittest.skipIf(sys.version_info < (3, 4), 'find spec() unavailable')
    def test_importlib_find_spec(self):
        scan = ansible_mitogen.module_finder._scan_importlib_find_spec
        actual = scan(self.module_name, self.module_path, self.search_path)
        self.assertEqual(
            [(name, self.relpath(path), is_pkg) for name, path, is_pkg in actual],
            [
                ('ansible.module_utils.external1', 'external1.py', False),
                ('ansible.module_utils.external2', 'external2.py', False),
                ('ansible.module_utils.externalpkg', 'externalpkg/__init__.py', True),
                ('ansible.module_utils.externalpkg.extmod', 'externalpkg/extmod.py',False),
            ],
        )

    @unittest.skipIf(sys.version_info >= (3, 4), 'find spec() preferred')
    def test_imp_find_module(self):
        scan = ansible_mitogen.module_finder._scan_imp_find_module
        actual = scan(self.module_name, self.module_path, self.search_path)
        self.assertEqual(
            [(name, self.relpath(path), is_pkg) for name, path, is_pkg in actual],
            [
                ('ansible.module_utils.external1', 'external1.py', False),
                ('ansible.module_utils.external2', 'external2.py', False),
                ('ansible.module_utils.externalpkg', 'externalpkg/__init__.py', True),
                ('ansible.module_utils.externalpkg.extmod', 'externalpkg/extmod.py',False),
            ],
        )
