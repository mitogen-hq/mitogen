import inspect

import unittest2

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
        self.assertEquals(src, inspect.getsource(regular_mod))
        self.assertFalse(is_pkg)


class GetModuleViaSysModulesTest(testlib.TestCase):
    klass = mitogen.master.ModuleFinder

    def call(self, fullname):
        return self.klass()._get_module_via_sys_modules(fullname)

    def test_main(self):
        import __main__
        path, src, is_pkg = self.call('__main__')
        self.assertEquals(path, __main__.__file__)
        self.assertEquals(src, open(path).read())
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


class FindRelatedTest(testlib.TestCase):
    klass = mitogen.master.ModuleFinder

    def call(self, fullname):
        return self.klass().find_related(fullname)

    def test_simple(self):
        import mitogen.fakessh
        related = self.call('mitogen.fakessh')
        self.assertEquals(related, [
            'mitogen',
            'mitogen.core',
            'mitogen.master',
        ])

    def test_django_pkg(self):
        import django
        related = self.call('django')
        self.assertEquals(related, [
            'django.utils',
            'django.utils.lru_cache',
            'django.utils.version',
        ])

    def test_django_db(self):
        import django.db
        related = self.call('django.db')
        self.assertEquals(related, [
            'django',
            'django.conf',
            'django.conf.global_settings',
            'django.core',
            'django.core.exceptions',
            'django.core.signals',
            'django.db.utils',
            'django.dispatch',
            'django.dispatch.dispatcher',
            'django.dispatch.weakref_backports',
            'django.utils',
            'django.utils._os',
            'django.utils.deprecation',
            'django.utils.encoding',
            'django.utils.functional',
            'django.utils.inspect',
            'django.utils.lru_cache',
            'django.utils.module_loading',
            'django.utils.six',
            'django.utils.version',
        ])

    def test_django_db_models(self):
        import django.db.models
        related = self.call('django.db.models')
        self.assertEquals(related, [
            'django',
            'django.apps',
            'django.conf',
            'django.conf.global_settings',
            'django.core',
            'django.core.cache',
            'django.core.cache.backends',
            'django.core.cache.backends.base',
            'django.core.checks',
            'django.core.checks.caches',
            'django.core.checks.compatibility',
            'django.core.checks.compatibility.django_1_10',
            'django.core.checks.compatibility.django_1_8_0',
            'django.core.checks.database',
            'django.core.checks.model_checks',
            'django.core.checks.security',
            'django.core.checks.security.base',
            'django.core.checks.security.csrf',
            'django.core.checks.security.sessions',
            'django.core.checks.templates',
            'django.core.checks.urls',
            'django.core.checks.utils',
            'django.core.exceptions',
            'django.core.files',
            'django.core.files.base',
            'django.core.files.images',
            'django.core.files.locks',
            'django.core.files.move',
            'django.core.files.storage',
            'django.core.files.utils',
            'django.core.signals',
            'django.core.validators',
            'django.db',
            'django.db.backends',
            'django.db.backends.utils',
            'django.db.models.aggregates',
            'django.db.models.base',
            'django.db.models.constants',
            'django.db.models.deletion',
            'django.db.models.expressions',
            'django.db.models.fields',
            'django.db.models.fields.files',
            'django.db.models.fields.proxy',
            'django.db.models.fields.related',
            'django.db.models.fields.related_descriptors',
            'django.db.models.fields.related_lookups',
            'django.db.models.fields.reverse_related',
            'django.db.models.functions',
            'django.db.models.indexes',
            'django.db.models.lookups',
            'django.db.models.manager',
            'django.db.models.options',
            'django.db.models.query',
            'django.db.models.query_utils',
            'django.db.models.signals',
            'django.db.models.sql',
            'django.db.models.sql.constants',
            'django.db.models.sql.datastructures',
            'django.db.models.sql.query',
            'django.db.models.sql.subqueries',
            'django.db.models.sql.where',
            'django.db.models.utils',
            'django.db.transaction',
            'django.db.utils',
            'django.dispatch',
            'django.dispatch.dispatcher',
            'django.dispatch.weakref_backports',
            'django.forms',
            'django.forms.boundfield',
            'django.forms.fields',
            'django.forms.forms',
            'django.forms.formsets',
            'django.forms.models',
            'django.forms.renderers',
            'django.forms.utils',
            'django.forms.widgets',
            'django.template',
            'django.template.backends',
            'django.template.backends.base',
            'django.template.backends.django',
            'django.template.backends.jinja2',
            'django.template.base',
            'django.template.context',
            'django.template.engine',
            'django.template.exceptions',
            'django.template.library',
            'django.template.loader',
            'django.template.utils',
            'django.templatetags',
            'django.templatetags.static',
            'django.utils',
            'django.utils._os',
            'django.utils.crypto',
            'django.utils.datastructures',
            'django.utils.dateformat',
            'django.utils.dateparse',
            'django.utils.dates',
            'django.utils.datetime_safe',
            'django.utils.deconstruct',
            'django.utils.decorators',
            'django.utils.deprecation',
            'django.utils.duration',
            'django.utils.encoding',
            'django.utils.formats',
            'django.utils.functional',
            'django.utils.html',
            'django.utils.html_parser',
            'django.utils.http',
            'django.utils.inspect',
            'django.utils.ipv6',
            'django.utils.itercompat',
            'django.utils.lru_cache',
            'django.utils.module_loading',
            'django.utils.numberformat',
            'django.utils.safestring',
            'django.utils.six',
            'django.utils.text',
            'django.utils.timezone',
            'django.utils.translation',
            'django.utils.tree',
            'django.utils.version',
            'jinja2',
            'jinja2._compat',
            'jinja2.bccache',
            'jinja2.compiler',
            'jinja2.defaults',
            'jinja2.environment',
            'jinja2.exceptions',
            'jinja2.filters',
            'jinja2.idtracking',
            'jinja2.lexer',
            'jinja2.loaders',
            'jinja2.nodes',
            'jinja2.optimizer',
            'jinja2.parser',
            'jinja2.runtime',
            'jinja2.tests',
            'jinja2.utils',
            'jinja2.visitor',
            'markupsafe',
            'markupsafe._compat',
            'markupsafe._speedups',
            'pytz',
            'pytz.exceptions',
            'pytz.lazy',
            'pytz.tzfile',
            'pytz.tzinfo',
        ])

if __name__ == '__main__':
    unittest2.main()
