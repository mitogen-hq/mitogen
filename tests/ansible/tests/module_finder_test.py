import os.path
import shutil
import sys
import tempfile
import textwrap
import unittest

import ansible_mitogen.module_finder

ANSIBLE_BASE_DIR = os.path.abspath(os.path.join(__file__, '..', '..'))
ANSIBLE_MODULES_DIR = os.path.join(ANSIBLE_BASE_DIR, 'lib', 'modules')
ANSIBLE_MODULE_UTILS_DIR = os.path.join(ANSIBLE_BASE_DIR, 'lib', 'module_utils')


class ScanFromListTest(unittest.TestCase):
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


class WalkImportsTest(unittest.TestCase):
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


class ScanTest(unittest.TestCase):
    module_name = 'ansible_module_module_finder_test__this_should_not_matter'
    module_path = os.path.join(ANSIBLE_MODULES_DIR, 'module_finder_test.py')
    search_path = (
        'does_not_exist/module_utils',
        ANSIBLE_MODULE_UTILS_DIR,
    )

    @staticmethod
    def relpath(path):
        return os.path.relpath(path, ANSIBLE_MODULE_UTILS_DIR)

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


class CollectionScanTest(unittest.TestCase):
    prefix = 'ansible_collections.acme.tools.plugins.module_utils'

    def setUp(self):
        self.directory = tempfile.mkdtemp(prefix='mitogen-module-finder-')
        self.addCleanup(shutil.rmtree, self.directory)
        self.root = os.path.join(self.directory, 'collections')
        self.utils = os.path.join(self.directory, 'module_utils')
        self.module = self.write('module.py', '')
        self.search_path = (self.utils,)
        self.collection_roots = (self.root,)

    def write(self, relative, source):
        path = os.path.join(self.directory, relative)
        parent = os.path.dirname(path)
        if not os.path.isdir(parent):
            os.makedirs(parent)
        with open(path, 'w') as fp:
            fp.write(textwrap.dedent(source))
        return path

    def utility(self, relative, source='', root='collections'):
        return self.write(
            root + '/ansible_collections/acme/tools/plugins/module_utils/' + relative,
            source,
        )

    def scan(self, source, module_name='ansible_module_collection_test'):
        self.write('module.py', source)
        return dict((name, (path, is_package))
                    for name, path, is_package in
                    ansible_mitogen.module_finder.scan(
                        module_name, self.module, self.search_path,
                        collection_search_path=self.collection_roots,
                    ))

    def assertUtility(self, actual, relative, path, is_package=False):
        name = self.prefix + '.' + relative
        self.assertIn(name, actual)
        self.assertEqual(actual[name], (path, is_package))

    def test_explicit_roots_absolute_imports_and_namespace_directories(self):
        helper = self.utility('helper.py')
        self.assertNotIn(self.root, sys.path)
        actual = self.scan('''\
            from ansible_collections.acme.tools.plugins.module_utils import helper
        ''')
        self.assertUtility(actual, 'helper', helper)
        parts = 'ansible_collections.acme.tools.plugins.module_utils'.split('.')
        self.assertEqual(set(actual), set(
            ['.'.join(parts[:index]) for index in range(1, len(parts) + 1)] +
            [self.prefix + '.helper']
        ))
        for index in range(1, len(parts) + 1):
            self.assertEqual(actual['.'.join(parts[:index])], (
                os.path.join(self.root, *parts[:index]), True,
            ))

    def test_scanning_never_executes_collection_or_package_code(self):
        poison = "raise AssertionError('controller executed fixture code')\n"
        for relative in (
                'ansible_collections/__init__.py',
                'ansible_collections/acme/__init__.py',
                'ansible_collections/acme/tools/__init__.py',
                'ansible_collections/acme/tools/plugins/__init__.py'):
            self.write('collections/' + relative, poison)
        self.utility('__init__.py', poison)
        helper = self.utility('helper.py', poison)
        actual = self.scan('''\
            from ansible_collections.acme.tools.plugins.module_utils import helper
            raise AssertionError('controller executed entrypoint')
        ''')
        self.assertUtility(actual, 'helper', helper)
        for name in ('ansible_collections', 'ansible_collections.acme',
                     'ansible_collections.acme.tools'):
            self.assertEqual(actual[name], (
                os.path.join(self.root, *name.split('.')), True,
            ))

    def test_relative_transitive_cycles_and_function_local_imports(self):
        entry = self.utility('entry.py', '''\
            from .nested import first
        ''')
        first = self.utility('nested/first.py', '''\
            def deferred():
                from .. import last
        ''')
        last = self.utility('last.py', '''\
            from . import entry
        ''')
        actual = self.scan('''\
            from ansible_collections.acme.tools.plugins.module_utils import entry
        ''')
        self.assertUtility(actual, 'entry', entry)
        self.assertUtility(actual, 'nested.first', first)
        self.assertUtility(actual, 'last', last)

    def test_collection_to_builtin_to_collection_closure(self):
        entry = self.utility('entry.py', '''\
            from ansible.module_utils import bridge
        ''')
        bridge = self.write('module_utils/bridge.py', '''\
            from ansible_collections.acme.tools.plugins.module_utils import final
        ''')
        final = self.utility('final.py')
        actual = self.scan('''\
            from ansible_collections.acme.tools.plugins.module_utils import entry
        ''')
        self.assertUtility(actual, 'entry', entry)
        self.assertUtility(actual, 'final', final)
        self.assertEqual(actual['ansible.module_utils.bridge'], (bridge, False))

    def test_optional_import_and_fromlist_attribute_are_not_modules(self):
        helper = self.utility('helper.py', '''\
            VALUE = 1
        ''')
        actual = self.scan('''\
            from ansible_collections.acme.tools.plugins.module_utils.helper import VALUE
            try:
                from ansible_collections.acme.tools.plugins.module_utils import missing
            except ImportError:
                pass
        ''')
        self.assertUtility(actual, 'helper', helper)
        self.assertNotIn(self.prefix + '.helper.VALUE', actual)
        self.assertNotIn(self.prefix + '.missing', actual)

    def test_collection_entrypoint_uses_fullname_for_relative_imports(self):
        helper = self.utility('helper.py')
        module_name = 'ansible_collections.acme.tools.plugins.modules.example'
        actual = self.scan('''\
            from ..module_utils import helper
        ''', module_name=module_name)
        self.assertUtility(actual, 'helper', helper)
        self.assertNotIn(module_name, actual)
        self.assertNotIn('ansible_collections.acme.tools.plugins.modules', actual)

    def test_package_initializers_contribute_dependencies(self):
        package = self.utility('package/__init__.py', '''\
            from .. import sibling
            raise AssertionError('package initializer executed')
        ''')
        child = self.utility('package/child.py')
        sibling = self.utility('sibling.py')
        actual = self.scan('''\
            from ansible_collections.acme.tools.plugins.module_utils.package import child
        ''')
        self.assertUtility(actual, 'package', package, True)
        self.assertUtility(actual, 'package.child', child)
        self.assertUtility(actual, 'sibling', sibling)

    def test_first_collection_directory_wins_without_merging_versions(self):
        first = self.utility('chosen.py')
        self.utility('chosen.py', root='later')
        self.utility('only_later.py', root='later')
        self.collection_roots = (self.root, os.path.join(self.directory, 'later'))
        actual = self.scan('''\
            from ansible_collections.acme.tools.plugins.module_utils import chosen
            from ansible_collections.acme.tools.plugins.module_utils import only_later
        ''')
        self.assertUtility(actual, 'chosen', first)
        self.assertNotIn(self.prefix + '.only_later', actual)
