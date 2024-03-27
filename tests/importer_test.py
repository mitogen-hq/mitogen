import sys
import threading
import types
import zlib
import unittest

try:
    from unittest import mock
except ImportError:
    import mock

import mitogen.core
import mitogen.utils
from mitogen.core import b

import testlib
import simple_pkg.imports_replaces_self


class ImporterMixin(testlib.RouterMixin):
    modname = None

    def setUp(self):
        super(ImporterMixin, self).setUp()
        self.context = mock.Mock()
        self.importer = mitogen.core.Importer(self.router, self.context, '')

        # TODO: this is a horrendous hack. Without it, we can't deliver a
        # response to find_module() via _on_load_module() since find_module()
        # is still holding the lock. The tests need a nicer abstraction for
        # soemthing like "fake participant" that lets us have a mock master
        # that respects the execution model expected by the code -- probably
        # (grmph) including multiplexer thread and all.
        self.importer._lock = threading.RLock()

    def set_get_module_response(self, resp):
        def on_context_send(msg):
            self.context_send_msg = msg
            self.importer._on_load_module(
                mitogen.core.Message.pickled(resp)
            )
        self.context.send = on_context_send

    def tearDown(self):
        sys.modules.pop(self.modname, None)
        super(ImporterMixin, self).tearDown()


class InvalidNameTest(ImporterMixin, testlib.TestCase):
    modname = 'trailingdot.'
    # 0:fullname 1:pkg_present 2:path 3:compressed 4:related
    response = (modname, None, None, None, None)

    @unittest.skipIf(sys.version_info < (3, 4), 'Requires ModuleSpec, Python 3.4+')
    def test_find_spec_invalid(self):
        self.set_get_module_response(self.response)
        self.assertEqual(self.importer.find_spec(self.modname, path=None), None)


class MissingModuleTest(ImporterMixin, testlib.TestCase):
    modname = 'missing'
    # 0:fullname 1:pkg_present 2:path 3:compressed 4:related
    response = (modname, None, None, None, None)

    @unittest.skipIf(sys.version_info >= (3, 4), 'Superceded in Python 3.4+')
    def test_load_module_missing(self):
        self.set_get_module_response(self.response)
        self.assertRaises(ImportError, self.importer.load_module, self.modname)

    @unittest.skipIf(sys.version_info < (3, 4), 'Requires ModuleSpec, Python 3.4+')
    def test_find_spec_missing(self):
        """
        Importer should optimistically offer itself as a module loader
        when there are no disqualifying criteria.
        """
        import importlib.machinery
        self.set_get_module_response(self.response)
        spec = self.importer.find_spec(self.modname, path=None)
        self.assertIsInstance(spec, importlib.machinery.ModuleSpec)
        self.assertEqual(spec.name, self.modname)
        self.assertEqual(spec.loader, self.importer)

    @unittest.skipIf(sys.version_info < (3, 4), 'Requires ModuleSpec, Python 3.4+')
    def test_create_module_missing(self):
        import importlib.machinery
        self.set_get_module_response(self.response)
        spec = importlib.machinery.ModuleSpec(self.modname, self.importer)
        self.assertRaises(ImportError, self.importer.create_module, spec)


@unittest.skipIf(sys.version_info >= (3, 4), 'Superceded in Python 3.4+')
class LoadModuleTest(ImporterMixin, testlib.TestCase):
    data = zlib.compress(b("data = 1\n\n"))
    path = 'fake_module.py'
    modname = 'fake_module'

    # 0:fullname 1:pkg_present 2:path 3:compressed 4:related
    response = (modname, None, path, data, [])

    def test_module_added_to_sys_modules(self):
        self.set_get_module_response(self.response)
        mod = self.importer.load_module(self.modname)
        self.assertIs(sys.modules[self.modname], mod)
        self.assertIsInstance(mod, types.ModuleType)

    def test_module_file_set(self):
        self.set_get_module_response(self.response)
        mod = self.importer.load_module(self.modname)
        self.assertEqual(mod.__file__, 'master:' + self.path)

    def test_module_loader_set(self):
        self.set_get_module_response(self.response)
        mod = self.importer.load_module(self.modname)
        self.assertIs(mod.__loader__, self.importer)

    def test_module_package_unset(self):
        self.set_get_module_response(self.response)
        mod = self.importer.load_module(self.modname)
        self.assertIsNone(mod.__package__)


@unittest.skipIf(sys.version_info < (3, 4), 'Requires ModuleSpec, Python 3.4+')
class ModuleSpecTest(ImporterMixin, testlib.TestCase):
    data = zlib.compress(b("data = 1\n\n"))
    path = 'fake_module.py'
    modname = 'fake_module'

    # 0:fullname 1:pkg_present 2:path 3:compressed 4:related
    response = (modname, None, path, data, [])

    def test_module_attributes(self):
        import importlib.machinery
        self.set_get_module_response(self.response)
        spec = importlib.machinery.ModuleSpec(self.modname, self.importer)
        mod = self.importer.create_module(spec)
        self.assertIsInstance(mod, types.ModuleType)
        self.assertEqual(mod.__name__, 'fake_module')
        #self.assertFalse(hasattr(mod, '__file__'))


@unittest.skipIf(sys.version_info >= (3, 4), 'Superceded in Python 3.4+')
class LoadSubmoduleTest(ImporterMixin, testlib.TestCase):
    data = zlib.compress(b("data = 1\n\n"))
    path = 'fake_module.py'
    modname = 'mypkg.fake_module'
    # 0:fullname 1:pkg_present 2:path 3:compressed 4:related
    response = (modname, None, path, data, [])

    def test_module_package_unset(self):
        self.set_get_module_response(self.response)
        mod = self.importer.load_module(self.modname)
        self.assertEqual(mod.__package__, 'mypkg')


@unittest.skipIf(sys.version_info < (3, 4), 'Requires ModuleSpec, Python 3.4+')
class SubmoduleSpecTest(ImporterMixin, testlib.TestCase):
    data = zlib.compress(b("data = 1\n\n"))
    path = 'fake_module.py'
    modname = 'mypkg.fake_module'
    # 0:fullname 1:pkg_present 2:path 3:compressed 4:related
    response = (modname, None, path, data, [])

    def test_module_attributes(self):
        import importlib.machinery
        self.set_get_module_response(self.response)
        spec = importlib.machinery.ModuleSpec(self.modname, self.importer)
        mod = self.importer.create_module(spec)
        self.assertIsInstance(mod, types.ModuleType)
        self.assertEqual(mod.__name__, 'mypkg.fake_module')
        #self.assertFalse(hasattr(mod, '__file__'))


@unittest.skipIf(sys.version_info >= (3, 4), 'Superceded in Python 3.4+')
class LoadModulePackageTest(ImporterMixin, testlib.TestCase):
    data = zlib.compress(b("func = lambda: 1\n\n"))
    path = 'fake_pkg/__init__.py'
    modname = 'fake_pkg'
    # 0:fullname 1:pkg_present 2:path 3:compressed 4:related
    response = (modname, [], path, data, [])

    def test_module_file_set(self):
        self.set_get_module_response(self.response)
        mod = self.importer.load_module(self.modname)
        self.assertEqual(mod.__file__, 'master:' + self.path)

    def test_get_filename(self):
        self.set_get_module_response(self.response)
        mod = self.importer.load_module(self.modname)
        filename = mod.__loader__.get_filename(self.modname)
        self.assertEqual('master:fake_pkg/__init__.py', filename)

    def test_get_source(self):
        self.set_get_module_response(self.response)
        mod = self.importer.load_module(self.modname)
        source = mod.__loader__.get_source(self.modname)
        self.assertEqual(source,
            mitogen.core.to_text(zlib.decompress(self.data)))

    def test_module_loader_set(self):
        self.set_get_module_response(self.response)
        mod = self.importer.load_module(self.modname)
        self.assertIs(mod.__loader__, self.importer)

    def test_module_path_present(self):
        self.set_get_module_response(self.response)
        mod = self.importer.load_module(self.modname)
        self.assertEqual(mod.__path__, [])

    def test_module_package_set(self):
        self.set_get_module_response(self.response)
        mod = self.importer.load_module(self.modname)
        self.assertEqual(mod.__package__, self.modname)

    def test_module_data(self):
        self.set_get_module_response(self.response)
        mod = self.importer.load_module(self.modname)
        self.assertIsInstance(mod.func, types.FunctionType)
        self.assertEqual(mod.func.__module__, self.modname)


@unittest.skipIf(sys.version_info < (3, 4), 'Requires ModuleSpec, Python 3.4+')
class PackageSpecTest(ImporterMixin, testlib.TestCase):
    data = zlib.compress(b("func = lambda: 1\n\n"))
    path = 'fake_pkg/__init__.py'
    modname = 'fake_pkg'
    # 0:fullname 1:pkg_present 2:path 3:compressed 4:related
    response = (modname, [], path, data, [])

    def test_module_attributes(self):
        import importlib.machinery
        self.set_get_module_response(self.response)
        spec = importlib.machinery.ModuleSpec(self.modname, self.importer)
        mod = self.importer.create_module(spec)
        self.assertIsInstance(mod, types.ModuleType)
        self.assertEqual(mod.__name__, 'fake_pkg')
        #self.assertFalse(hasattr(mod, '__file__'))

    def test_get_filename(self):
        import importlib.machinery
        self.set_get_module_response(self.response)
        spec = importlib.machinery.ModuleSpec(self.modname, self.importer)
        _ = self.importer.create_module(spec)
        filename = self.importer.get_filename(self.modname)
        self.assertEqual('master:fake_pkg/__init__.py', filename)

    def test_get_source(self):
        import importlib.machinery
        self.set_get_module_response(self.response)
        spec = importlib.machinery.ModuleSpec(self.modname, self.importer)
        _ = self.importer.create_module(spec)
        source = self.importer.get_source(self.modname)
        self.assertEqual(source,
            mitogen.core.to_text(zlib.decompress(self.data)))


class EmailParseAddrSysTest(testlib.RouterMixin, testlib.TestCase):
    def initdir(self, caplog):
        self.caplog = caplog

    def test_sys_module_not_fetched(self):
        # An old version of core.Importer would request the email.sys module
        # while executing email.utils.parseaddr(). Ensure this needless
        # roundtrip has not reappeared.
        pass


class ImporterBlacklistTest(testlib.TestCase):
    def test_is_blacklisted_import_default(self):
        importer = mitogen.core.Importer(
            router=mock.Mock(), context=None, core_src='',
        )
        self.assertIsInstance(importer.whitelist, list)
        self.assertIsInstance(importer.blacklist, list)
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
        self.assertIsInstance(importer.whitelist, list)
        self.assertIsInstance(importer.blacklist, list)
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
        self.assertIsInstance(importer.whitelist, list)
        self.assertIsInstance(importer.blacklist, list)
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
        self.assertIsInstance(importer.whitelist, list)
        self.assertIsInstance(importer.blacklist, list)
        self.assertTrue(mitogen.core.is_blacklisted_import(importer, 'mypkg'))
        self.assertTrue(mitogen.core.is_blacklisted_import(importer, 'mypkg.mod'))
        self.assertTrue(mitogen.core.is_blacklisted_import(importer, 'otherpkg'))
        self.assertTrue(mitogen.core.is_blacklisted_import(importer, 'otherpkg.mod'))
        self.assertTrue(mitogen.core.is_blacklisted_import(importer, '__builtin__'))
        self.assertTrue(mitogen.core.is_blacklisted_import(importer, 'builtins'))


class Python24LineCacheTest(testlib.TestCase):
    # TODO: mitogen.core.Importer._update_linecache()
    pass


class SelfReplacingModuleTest(testlib.RouterMixin, testlib.TestCase):
    # issue #590
    def test_importer_handles_self_replacement(self):
        c = self.router.local()
        self.assertEqual(0,
            c.call(simple_pkg.imports_replaces_self.subtract_one, 1))
