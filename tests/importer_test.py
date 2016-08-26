
import email.utils
import sys
import types
import unittest
import zlib

import mock
import pytest

import econtext.core
import testlib


class ImporterMixin(object):
    modname = None

    def setUp(self):
        super(ImporterMixin, self).setUp()
        self.context = mock.Mock()
        self.importer = econtext.core.Importer(self.context)

    def tearDown(self):
        sys.modules.pop(self.modname, None)
        super(ImporterMixin, self).tearDown()


class LoadModuleTest(ImporterMixin, unittest.TestCase):
    data = zlib.compress("data = 1\n\n")
    path = 'fake_module.py'
    modname = 'fake_module'
    response = (None, path, data)

    def test_no_such_module(self):
        self.context.enqueue_await_reply.return_value = None
        self.assertRaises(ImportError,
            lambda: self.importer.load_module(self.modname))

    def test_module_added_to_sys_modules(self):
        self.context.enqueue_await_reply.return_value = self.response
        mod = self.importer.load_module(self.modname)
        self.assertTrue(sys.modules[self.modname] is mod)
        self.assertTrue(isinstance(mod, types.ModuleType))

    def test_module_file_set(self):
        self.context.enqueue_await_reply.return_value = self.response
        mod = self.importer.load_module(self.modname)
        self.assertEquals(mod.__file__, 'master:' + self.path)

    def test_module_loader_set(self):
        self.context.enqueue_await_reply.return_value = self.response
        mod = self.importer.load_module(self.modname)
        self.assertTrue(mod.__loader__ is self.importer)

    def test_module_package_unset(self):
        self.context.enqueue_await_reply.return_value = self.response
        mod = self.importer.load_module(self.modname)
        self.assertTrue(mod.__package__ is None)


class LoadSubmoduleTest(ImporterMixin, unittest.TestCase):
    data = zlib.compress("data = 1\n\n")
    path = 'fake_module.py'
    modname = 'mypkg.fake_module'
    response = (None, path, data)

    def test_module_package_unset(self):
        self.context.enqueue_await_reply.return_value = self.response
        mod = self.importer.load_module(self.modname)
        self.assertEquals(mod.__package__, 'mypkg')


class LoadModulePackageTest(ImporterMixin, unittest.TestCase):
    data = zlib.compress("func = lambda: 1\n\n")
    path = 'fake_pkg/__init__.py'
    modname = 'fake_pkg'
    response = ([], path, data)

    def test_module_file_set(self):
        self.context.enqueue_await_reply.return_value = self.response
        mod = self.importer.load_module(self.modname)
        self.assertEquals(mod.__file__, 'master:' + self.path)

    def test_get_filename(self):
        self.context.enqueue_await_reply.return_value = self.response
        mod = self.importer.load_module(self.modname)
        filename = mod.__loader__.get_filename(self.modname)
        self.assertEquals('master:fake_pkg/__init__.py', filename)

    def test_get_source(self):
        self.context.enqueue_await_reply.return_value = self.response
        mod = self.importer.load_module(self.modname)
        source = mod.__loader__.get_source(self.modname)
        self.assertEquals(source, zlib.decompress(self.data))

    def test_module_loader_set(self):
        self.context.enqueue_await_reply.return_value = self.response
        mod = self.importer.load_module(self.modname)
        self.assertTrue(mod.__loader__ is self.importer)

    def test_module_path_present(self):
        self.context.enqueue_await_reply.return_value = self.response
        mod = self.importer.load_module(self.modname)
        self.assertEquals(mod.__path__, [])

    def test_module_package_set(self):
        self.context.enqueue_await_reply.return_value = self.response
        mod = self.importer.load_module(self.modname)
        self.assertEquals(mod.__package__, self.modname)

    def test_module_data(self):
        self.context.enqueue_await_reply.return_value = self.response
        mod = self.importer.load_module(self.modname)
        self.assertTrue(isinstance(mod.func, types.FunctionType))
        self.assertEquals(mod.func.__module__, self.modname)


class EmailParseAddrSysTest(testlib.BrokerMixin, unittest.TestCase):
    @pytest.fixture(autouse=True)
    def initdir(self, caplog):
        self.caplog = caplog

    def test_sys_module_not_fetched(self):
        # An old version of core.Importer would request the email.sys module
        # while executing email.utils.parseaddr(). Ensure this needless
        # roundtrip has not reappeared.
        pass
