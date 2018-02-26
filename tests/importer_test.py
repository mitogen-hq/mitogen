
import email.utils
import sys
import types
import zlib

import mock
import pytest
import unittest2

import mitogen.core
import mitogen.utils

import testlib


class ImporterMixin(testlib.RouterMixin):
    modname = None

    def setUp(self):
        super(ImporterMixin, self).setUp()
        self.context = mock.Mock()
        self.importer = mitogen.core.Importer(self.router, self.context, '')

    def tearDown(self):
        sys.modules.pop(self.modname, None)
        super(ImporterMixin, self).tearDown()


class ImporterBlacklist(testlib.TestCase):
    def test_is_blacklisted_import_default(self):
        importer = mitogen.core.Importer(
            router=mock.Mock(), context=None, core_src='',
        )
        self.assertFalse(mitogen.core.is_blacklisted_import(importer, 'mypkg'))
        self.assertFalse(mitogen.core.is_blacklisted_import(importer, 'mypkg.mod'))
        self.assertFalse(mitogen.core.is_blacklisted_import(importer, 'otherpkg'))
        self.assertFalse(mitogen.core.is_blacklisted_import(importer, 'otherpkg.mod'))
        self.assertTrue(mitogen.core.is_blacklisted_import(importer, '__builtin__'))
        self.assertTrue(mitogen.core.is_blacklisted_import(importer, 'builtins'))

    def test_is_blacklisted_import_just_whitelist(self):
        importer = mitogen.core.Importer(
            router=mock.Mock(), context=None, core_src='',
            whitelist=('mypkg',),
        )
        self.assertFalse(mitogen.core.is_blacklisted_import(importer, 'mypkg'))
        self.assertFalse(mitogen.core.is_blacklisted_import(importer, 'mypkg.mod'))
        self.assertTrue(mitogen.core.is_blacklisted_import(importer, 'otherpkg'))
        self.assertTrue(mitogen.core.is_blacklisted_import(importer, 'otherpkg.mod'))
        self.assertTrue(mitogen.core.is_blacklisted_import(importer, '__builtin__'))
        self.assertTrue(mitogen.core.is_blacklisted_import(importer, 'builtins'))

    def test_is_blacklisted_import_just_blacklist(self):
        importer = mitogen.core.Importer(
            router=mock.Mock(), context=None, core_src='',
            blacklist=('mypkg',),
        )
        self.assertTrue(mitogen.core.is_blacklisted_import(importer, 'mypkg'))
        self.assertTrue(mitogen.core.is_blacklisted_import(importer, 'mypkg.mod'))
        self.assertFalse(mitogen.core.is_blacklisted_import(importer, 'otherpkg'))
        self.assertFalse(mitogen.core.is_blacklisted_import(importer, 'otherpkg.mod'))
        self.assertTrue(mitogen.core.is_blacklisted_import(importer, '__builtin__'))
        self.assertTrue(mitogen.core.is_blacklisted_import(importer, 'builtins'))

    def test_is_blacklisted_import_whitelist_and_blacklist(self):
        importer = mitogen.core.Importer(
            router=mock.Mock(), context=None, core_src='',
            whitelist=('mypkg',), blacklist=('mypkg',),
        )
        self.assertTrue(mitogen.core.is_blacklisted_import(importer, 'mypkg'))
        self.assertTrue(mitogen.core.is_blacklisted_import(importer, 'mypkg.mod'))
        self.assertTrue(mitogen.core.is_blacklisted_import(importer, 'otherpkg'))
        self.assertTrue(mitogen.core.is_blacklisted_import(importer, 'otherpkg.mod'))
        self.assertTrue(mitogen.core.is_blacklisted_import(importer, '__builtin__'))
        self.assertTrue(mitogen.core.is_blacklisted_import(importer, 'builtins'))


class LoadModuleTest(ImporterMixin, testlib.TestCase):
    data = zlib.compress("data = 1\n\n")
    path = 'fake_module.py'
    modname = 'fake_module'
    response = (None, path, data)

    def test_no_such_module(self):
        self.context.send_await.return_value = None
        self.assertRaises(ImportError,
            lambda: self.importer.load_module(self.modname))

    def test_module_added_to_sys_modules(self):
        self.context.send_await.return_value = self.response
        mod = self.importer.load_module(self.modname)
        self.assertIs(sys.modules[self.modname], mod)
        self.assertIsInstance(mod, types.ModuleType)

    def test_module_file_set(self):
        self.context.send_await.return_value = self.response
        mod = self.importer.load_module(self.modname)
        self.assertEquals(mod.__file__, 'master:' + self.path)

    def test_module_loader_set(self):
        self.context.send_await.return_value = self.response
        mod = self.importer.load_module(self.modname)
        self.assertIs(mod.__loader__, self.importer)

    def test_module_package_unset(self):
        self.context.send_await.return_value = self.response
        mod = self.importer.load_module(self.modname)
        self.assertIsNone(mod.__package__)


class LoadSubmoduleTest(ImporterMixin, testlib.TestCase):
    data = zlib.compress("data = 1\n\n")
    path = 'fake_module.py'
    modname = 'mypkg.fake_module'
    response = (None, path, data)

    def test_module_package_unset(self):
        self.context.send_await.return_value = self.response
        mod = self.importer.load_module(self.modname)
        self.assertEquals(mod.__package__, 'mypkg')


class LoadModulePackageTest(ImporterMixin, testlib.TestCase):
    data = zlib.compress("func = lambda: 1\n\n")
    path = 'fake_pkg/__init__.py'
    modname = 'fake_pkg'
    response = ([], path, data)

    def test_module_file_set(self):
        self.context.send_await.return_value = self.response
        mod = self.importer.load_module(self.modname)
        self.assertEquals(mod.__file__, 'master:' + self.path)

    def test_get_filename(self):
        self.context.send_await.return_value = self.response
        mod = self.importer.load_module(self.modname)
        filename = mod.__loader__.get_filename(self.modname)
        self.assertEquals('master:fake_pkg/__init__.py', filename)

    def test_get_source(self):
        self.context.send_await.return_value = self.response
        mod = self.importer.load_module(self.modname)
        source = mod.__loader__.get_source(self.modname)
        self.assertEquals(source, zlib.decompress(self.data))

    def test_module_loader_set(self):
        self.context.send_await.return_value = self.response
        mod = self.importer.load_module(self.modname)
        self.assertIs(mod.__loader__, self.importer)

    def test_module_path_present(self):
        self.context.send_await.return_value = self.response
        mod = self.importer.load_module(self.modname)
        self.assertEquals(mod.__path__, [])

    def test_module_package_set(self):
        self.context.send_await.return_value = self.response
        mod = self.importer.load_module(self.modname)
        self.assertEquals(mod.__package__, self.modname)

    def test_module_data(self):
        self.context.send_await.return_value = self.response
        mod = self.importer.load_module(self.modname)
        self.assertIsInstance(mod.func, types.FunctionType)
        self.assertEquals(mod.func.__module__, self.modname)


class EmailParseAddrSysTest(testlib.RouterMixin, testlib.TestCase):
    @pytest.fixture(autouse=True)
    def initdir(self, caplog):
        self.caplog = caplog

    def test_sys_module_not_fetched(self):
        # An old version of core.Importer would request the email.sys module
        # while executing email.utils.parseaddr(). Ensure this needless
        # roundtrip has not reappeared.
        pass


if __name__ == '__main__':
    unittest2.main()
