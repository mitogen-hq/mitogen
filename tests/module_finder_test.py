
import unittest
import mitogen.master

import testlib


class ConstructorTest(testlib.TestCase):
    klass = mitogen.master.ModuleFinder

    def test_simple(self):
        self.klass()


class ReprTest(testlib.TestCase):
    klass = mitogen.master.ModuleFinder

    def test_simple(self):
        self.assertEquals('ModuleFinder()', repr(self.klass()))


class IsStdlibNameTest(testlib.TestCase):
    klass = mitogen.master.ModuleFinder

    def call(self, fullname):
        return self.klass().is_stdlib_name(fullname)

    def test_builtin(self):
        import sys
        self.assertTrue(self.call('sys'))

    def test_stdlib_1(self):
        import logging
        self.assertTrue(self.call('logging'))

    def test_stdlib_2(self):
        # virtualenv only symlinks some paths to its local site-packages
        # directory. Ensure both halves of the search path return the correct
        # result.
        import email
        self.assertTrue(self.call('email'))

    def test_mitogen_core(self):
        import mitogen.core
        self.assertFalse(self.call('mitogen.core'))

    def test_mitogen_fakessh(self):
        import mitogen.fakessh
        self.assertFalse(self.call('mitogen.fakessh'))


class GetModuleViaPkgutilTest(testlib.TestCase):
    klass = mitogen.master.ModuleFinder

    def call(self, fullname):
        return self.klass()._get_module_via_pkgutil(fullname)

    def test_empty_source_pkg(self):
        path, src, is_pkg = self.call('module_finder_testmod')
        self.assertEquals(path,
            testlib.data_path('module_finder_testmod/__init__.py'))
        self.assertEquals('', src)
        self.assertTrue(is_pkg)

    def test_empty_source_module(self):
        path, src, is_pkg = self.call('module_finder_testmod.empty_mod')
        self.assertEquals(path,
            testlib.data_path('module_finder_testmod/empty_mod.py'))
        self.assertEquals('', src)
        self.assertFalse(is_pkg)

    def test_regular_mod(self):
        from module_finder_testmod import regular_mod
        path, src, is_pkg = self.call('module_finder_testmod.regular_mod')
        self.assertEquals(path,
            testlib.data_path('module_finder_testmod/regular_mod.py'))
        self.assertEquals(src, file(regular_mod.__file__).read())
        self.assertFalse(is_pkg)


class GetModuleViaSysModulesTest(testlib.TestCase):
    klass = mitogen.master.ModuleFinder

    def call(self, fullname):
        return self.klass()._get_module_via_sys_modules(fullname)

    def test_main(self):
        import __main__
        path, src, is_pkg = self.call('__main__')
        self.assertEquals(path, __main__.__file__)
        self.assertEquals(src, file(path).read())
        self.assertFalse(is_pkg)

    def test_dylib_fails(self):
        # _socket comes from a .so
        import _socket
        tup = self.call('_socket')
        self.assertEquals(None, tup)

    def test_builtin_fails(self):
        # sys is built-in
        tup = self.call('sys')
        self.assertEquals(None, tup)


class ResolveRelPathTest(testlib.TestCase):
    klass = mitogen.master.ModuleFinder

    def call(self, fullname, level):
        return self.klass().resolve_relpath(fullname, level)

    def test_empty(self):
        self.assertEquals('', self.call('', 0))
        self.assertEquals('', self.call('', 1))
        self.assertEquals('', self.call('', 2))

    def test_absolute(self):
        self.assertEquals('', self.call('email.utils', 0))

    def test_rel1(self):
        self.assertEquals('email.', self.call('email.utils', 1))

    def test_rel2(self):
        self.assertEquals('', self.call('email.utils', 2))

    def test_rel_overflow(self):
        self.assertEquals('', self.call('email.utils', 3))


class FindRelatedImportsTest(testlib.TestCase):
    klass = mitogen.master.ModuleFinder

    def call(self, fullname):
        return self.klass().find_related_imports(fullname)

    def test_simple(self):
        import mitogen.fakessh
        related = self.call('mitogen.fakessh')
        self.assertEquals(related, [
            'mitogen',
            'mitogen.core',
            'mitogen.master',
        ])


if __name__ == '__main__':
    unittest.main()
