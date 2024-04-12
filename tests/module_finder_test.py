import inspect
import json
import os
import sys
import unittest

import mitogen.master
from mitogen.core import b

import testlib


class ConstructorTest(testlib.TestCase):
    klass = mitogen.master.ModuleFinder

    def test_simple(self):
        self.klass()


class ReprTest(testlib.TestCase):
    klass = mitogen.master.ModuleFinder

    def test_simple(self):
        self.assertEqual('ModuleFinder()', repr(self.klass()))


class IsStdlibNameTest(testlib.TestCase):
    func = staticmethod(mitogen.master.is_stdlib_name)

    def test_builtin(self):
        import sys
        self.assertTrue(self.func('sys'))

    def test_stdlib_1(self):
        import logging
        self.assertTrue(self.func('logging'))

    def test_stdlib_2(self):
        # virtualenv only symlinks some paths to its local site-packages
        # directory. Ensure both halves of the search path return the correct
        # result.
        import email
        self.assertTrue(self.func('email'))

    def test_mitogen_core(self):
        import mitogen.core
        self.assertFalse(self.func('mitogen.core'))

    def test_mitogen_fakessh(self):
        import mitogen.fakessh
        self.assertFalse(self.func('mitogen.fakessh'))


class GetMainModuleDefectivePython3x(testlib.TestCase):
    klass = mitogen.master.DefectivePython3xMainMethod

    def call(self, fullname):
        return self.klass().find(fullname)

    def test_builtin(self):
        self.assertEqual(None, self.call('sys'))

    def test_not_main(self):
        self.assertEqual(None, self.call('mitogen'))

    def test_main(self):
        import __main__

        path, source, is_pkg = self.call('__main__')
        self.assertIsNotNone(path)
        self.assertTrue(os.path.exists(path))
        self.assertEqual(path, __main__.__file__)
        fp = open(path, 'rb')
        try:
            self.assertEqual(source, fp.read())
        finally:
            fp.close()
        self.assertFalse(is_pkg)


class PkgutilMethodTest(testlib.TestCase):
    klass = mitogen.master.PkgutilMethod

    def call(self, fullname):
        return self.klass().find(fullname)

    def test_empty_source_pkg(self):
        path, src, is_pkg = self.call('module_finder_testmod')
        self.assertEqual(path,
            os.path.join(testlib.MODS_DIR, 'module_finder_testmod/__init__.py'))
        self.assertEqual(mitogen.core.b(''), src)
        self.assertTrue(is_pkg)

    def test_empty_source_module(self):
        path, src, is_pkg = self.call('module_finder_testmod.empty_mod')
        self.assertEqual(path,
            os.path.join(testlib.MODS_DIR, 'module_finder_testmod/empty_mod.py'))
        self.assertEqual(mitogen.core.b(''), src)
        self.assertFalse(is_pkg)

    def test_regular_mod(self):
        from module_finder_testmod import regular_mod
        path, src, is_pkg = self.call('module_finder_testmod.regular_mod')
        self.assertEqual(path,
            os.path.join(testlib.MODS_DIR, 'module_finder_testmod/regular_mod.py'))
        self.assertEqual(mitogen.core.to_text(src),
                          inspect.getsource(regular_mod))
        self.assertFalse(is_pkg)


class SysModulesMethodTest(testlib.TestCase):
    klass = mitogen.master.SysModulesMethod

    def call(self, fullname):
        return self.klass().find(fullname)

    def test_main(self):
        import __main__
        path, src, is_pkg = self.call('__main__')
        self.assertEqual(path, __main__.__file__)

        # linecache adds a line ending to the final line if one is missing.
        with open(path, 'rb') as f:
            actual_src = f.read()
        if actual_src[-1:] != b('\n'):
            actual_src += b('\n')

        self.assertEqual(src, actual_src)
        self.assertFalse(is_pkg)

    def test_dylib_fails(self):
        # _socket comes from a .so
        import _socket
        tup = self.call('_socket')
        self.assertIsNone(tup)

    def test_builtin_fails(self):
        # sys is built-in
        tup = self.call('sys')
        self.assertIsNone(tup)


class ParentEnumerationMixin(object):
    def call(self, fullname):
        return self.klass().find(fullname)

    def test_main_fails(self):
        import __main__
        self.assertIsNone(self.call('__main__'))

    def test_dylib_fails(self):
        # _socket comes from a .so
        import _socket
        tup = self.call('_socket')
        self.assertIsNone(tup)

    def test_builtin_fails(self):
        # sys is built-in
        tup = self.call('sys')
        self.assertIsNone(tup)

    def test_plumbum_colors_like_pkg_succeeds(self):
        # plumbum has been eating too many rainbow-colored pills
        import pkg_like_plumbum.colors
        path, src, is_pkg = self.call('pkg_like_plumbum.colors')
        modpath = os.path.join(testlib.MODS_DIR, 'pkg_like_plumbum/colors.py')
        self.assertEqual(path, modpath)

        with open(modpath, 'rb') as f:
            self.assertEqual(src, f.read())
        self.assertFalse(is_pkg)

    def test_ansible_module_utils_distro_succeeds(self):
        # #590: a package that turns itself into a module.
        import pkg_like_ansible.module_utils.distro as d
        self.assertEqual(d.I_AM, "the module that replaced the package")
        self.assertEqual(
            sys.modules['pkg_like_ansible.module_utils.distro'].__name__,
            'pkg_like_ansible.module_utils.distro._distro'
        )

        # ensure we can resolve the subpackage.
        path, src, is_pkg = self.call('pkg_like_ansible.module_utils.distro')
        modpath = os.path.join(testlib.MODS_DIR,
            'pkg_like_ansible/module_utils/distro/__init__.py')
        self.assertEqual(path, modpath)
        with open(modpath, 'rb') as f:
            self.assertEqual(src, f.read())
        self.assertEqual(is_pkg, True)

        # ensure we can resolve a child of the subpackage.
        path, src, is_pkg = self.call(
            'pkg_like_ansible.module_utils.distro._distro'
        )
        modpath = os.path.join(testlib.MODS_DIR,
            'pkg_like_ansible/module_utils/distro/_distro.py')
        self.assertEqual(path, modpath)
        with open(modpath, 'rb') as f:
            self.assertEqual(src, f.read())
        self.assertEqual(is_pkg, False)

    def test_ansible_module_utils_system_distro_succeeds(self):
        # #590: a package that turns itself into a module.
        # #590: a package that turns itself into a module.
        import pkg_like_ansible.module_utils.sys_distro as d
        self.assertEqual(d.I_AM, "the system module that replaced the subpackage")
        self.assertEqual(
            sys.modules['pkg_like_ansible.module_utils.sys_distro'].__name__,
            'system_distro'
        )

        # ensure we can resolve the subpackage.
        path, src, is_pkg = self.call('pkg_like_ansible.module_utils.sys_distro')
        modpath = os.path.join(testlib.MODS_DIR,
            'pkg_like_ansible/module_utils/sys_distro/__init__.py')
        self.assertEqual(path, modpath)
        with open(modpath, 'rb') as f:
            self.assertEqual(src, f.read())
        self.assertEqual(is_pkg, True)

        # ensure we can resolve a child of the subpackage.
        path, src, is_pkg = self.call(
            'pkg_like_ansible.module_utils.sys_distro._distro'
        )
        modpath = os.path.join(testlib.MODS_DIR,
            'pkg_like_ansible/module_utils/sys_distro/_distro.py')
        self.assertEqual(path, modpath)
        with open(modpath, 'rb') as f:
            self.assertEqual(src, f.read())
        self.assertEqual(is_pkg, False)


@unittest.skipIf(sys.version_info >= (3, 4), 'Superceded in Python >= 3.4')
class ParentImpEnumerationMethodTest(ParentEnumerationMixin, testlib.TestCase):
    klass = mitogen.master.ParentImpEnumerationMethod


@unittest.skipIf(sys.version_info < (3, 4), 'Requires ModuleSpec, Python 3.4+')
class ParentSpecEnumerationMethodTest(ParentEnumerationMixin, testlib.TestCase):
    klass = mitogen.master.ParentSpecEnumerationMethod


class ResolveRelPathTest(testlib.TestCase):
    klass = mitogen.master.ModuleFinder

    def call(self, fullname, level):
        return self.klass().resolve_relpath(fullname, level)

    def test_empty(self):
        self.assertEqual('', self.call('', 0))
        self.assertEqual('', self.call('', 1))
        self.assertEqual('', self.call('', 2))

    def test_absolute(self):
        self.assertEqual('', self.call('email.utils', 0))

    def test_rel1(self):
        self.assertEqual('email.', self.call('email.utils', 1))

    def test_rel2(self):
        self.assertEqual('', self.call('email.utils', 2))

    def test_rel_overflow(self):
        self.assertEqual('', self.call('email.utils', 3))


class FakeSshTest(testlib.TestCase):
    klass = mitogen.master.ModuleFinder

    def call(self, fullname):
        return self.klass().find_related_imports(fullname)

    def test_simple(self):
        import mitogen.fakessh
        related = self.call('mitogen.fakessh')
        self.assertEqual(related, [
            'mitogen',
            'mitogen.core',
            'mitogen.parent',
        ])


class FindRelatedTest(testlib.TestCase):
    klass = mitogen.master.ModuleFinder

    def call(self, fullname):
        return self.klass().find_related(fullname)

    SIMPLE_EXPECT = set([
        u'mitogen',
        u'mitogen.core',
        u'mitogen.parent',
    ])

    if sys.version_info < (2, 7):
        SIMPLE_EXPECT.add('mitogen.compat')
        SIMPLE_EXPECT.add('mitogen.compat.tokenize')
    if sys.version_info < (2, 6):
        SIMPLE_EXPECT.add('mitogen.compat')
        SIMPLE_EXPECT.add('mitogen.compat.pkgutil')

    def test_simple(self):
        import mitogen.fakessh
        related = self.call('mitogen.fakessh')
        self.assertEqual(set(related), self.SIMPLE_EXPECT)


class DjangoMixin(object):
    WEBPROJECT_PATH = os.path.join(testlib.MODS_DIR, 'webproject')

    @classmethod
    def modules_expected_path(cls):
        if sys.version_info[0:2] < (3, 0):
            modules_expected_filename = 'modules_expected_py2x.json'
        elif sys.version_info[0:2] <= (3, 6):
            modules_expected_filename = 'modules_expected_py3x-legacy.json'
        elif sys.version_info[0:2] >= (3, 10):
            modules_expected_filename = 'modules_expected_py3x-new.json'
        return os.path.join(cls.WEBPROJECT_PATH, modules_expected_filename)

    @classmethod
    def setUpClass(cls):
        super(DjangoMixin, cls).setUpClass()
        sys.path.append(cls.WEBPROJECT_PATH)
        os.environ['DJANGO_SETTINGS_MODULE'] = 'webproject.settings'
        with open(cls.modules_expected_path(), 'rb') as f:
            cls.MODULES_EXPECTED = json.load(f)

    @classmethod
    def tearDownClass(cls):
        sys.path.remove(cls.WEBPROJECT_PATH)
        del os.environ['DJANGO_SETTINGS_MODULE']
        super(DjangoMixin, cls).tearDownClass()


class DjangoFindRelatedTest(DjangoMixin, testlib.TestCase):
    maxDiff = None

    def test_django_db(self):
        import django.db
        module_finder = mitogen.master.ModuleFinder()
        related = module_finder.find_related('django.db')
        expected = self.MODULES_EXPECTED['find_related']['django.db']
        self.assertEqual(related, expected)

    def test_django_db_models(self):
        import django.db.models
        module_finder = mitogen.master.ModuleFinder()
        related = module_finder.find_related('django.db.models')
        expected = self.MODULES_EXPECTED['find_related']['django.db.models']
        self.assertEqual(related, expected)


class DjangoFindRelatedImportsTest(DjangoMixin, testlib.TestCase):
    maxDiff = None

    def test_django_db(self):
        import django.db
        module_finder = mitogen.master.ModuleFinder()
        related = module_finder.find_related_imports('django.db')
        expected = self.MODULES_EXPECTED['find_related_imports']['django.db']
        self.assertEqual(related, expected)

    def test_django_db_models(self):
        import django.db.models
        module_finder = mitogen.master.ModuleFinder()
        related = module_finder.find_related_imports('django.db.models')
        expected = self.MODULES_EXPECTED['find_related_imports']['django.db.models']
        self.assertEqual(related, expected)
