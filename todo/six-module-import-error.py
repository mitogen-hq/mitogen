[11:46:20 Eldil!8 econtext] py.test tests/ssh_test.py
=============================================================================== test session starts ================================================================================
platform darwin -- Python 2.7.10, pytest-2.8.6, py-1.4.31, pluggy-0.3.1
rootdir: /Users/dmw/src/econtext, inifile:
plugins: capturelog-0.7, timeout-1.0.0
collected 1 items

tests/ssh_test.py F

===================================================================================== FAILURES =====================================================================================
________________________________________________________________________________ SshTest.test_okay _________________________________________________________________________________

self = <ssh_test.SshTest testMethod=test_okay>

    def test_okay(self):
>       @econtext.utils.run_with_broker
        def test(broker):

tests/ssh_test.py:18:
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _
econtext/utils.py:52: in run_with_broker
    return func(broker, *args, **kwargs)
tests/ssh_test.py:25: in test
    self.assertEquals(3, context.call(add, 1, 2))
econtext/master.py:319: in call
    return self.call_with_deadline(None, False, fn, *args, **kwargs)
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _

self = Context('hostname', 'hostname'), deadline = None, with_context = False, fn = <function add at 0x1023630c8>, args = (1, 2), kwargs = {}, klass = None
call = (False, 'ssh_test', None, 'add', (1, 2), {})
result = CallError('call failed: __builtin__.str: call failed: exceptions.KeyError: \'p...ern/__init__.py", line 43, in load_module\n    mod = sys.modules[extant]\n\n',)

    def call_with_deadline(self, deadline, with_context, fn, *args, **kwargs):
        """Invoke `fn([context,] *args, **kwargs)` in the external context.

            If `with_context` is ``True``, pass its
            :py:class:`ExternalContext <econtext.core.ExternalContext>` instance as
            the first parameter.

            If `deadline` is not ``None``, expire the call after `deadline`
            seconds. If `deadline` is ``None``, the invocation may block
            indefinitely."""
        LOG.debug('%r.call_with_deadline(%r, %r, %r, *%r, **%r)',
                  self, deadline, with_context, fn, args, kwargs)

        if isinstance(fn, types.MethodType) and \
           isinstance(fn.im_self, (type, types.ClassType)):
            klass = fn.im_self.__name__
        else:
            klass = None

        call = (with_context, fn.__module__, klass, fn.__name__, args, kwargs)
        result = self.enqueue_await_reply(econtext.core.CALL_FUNCTION,
                                          deadline, call)
        if isinstance(result, econtext.core.CallError):
>           raise result
E           CallError: call failed: __builtin__.str: call failed: exceptions.KeyError: 'pkg_resources._vendor.six.moves.'
E             File "<stdin>", line 862, in _dispatch_calls
E             File "<stdin>", line 220, in load_module
E             File "master:/Users/dmw/src/econtext/tests/ssh_test.py", line 9, in <module>
E               import testlib
E             File "<stdin>", line 220, in load_module
E             File "master:/Users/dmw/src/econtext/tests/testlib.py", line 6, in <module>
E               import mock
E             File "<stdin>", line 220, in load_module
E             File "master:/Users/dmw/.venv/lib/python2.7/site-packages/mock/__init__.py", line 2, in <module>
E               import mock.mock as _mock
E             File "<stdin>", line 220, in load_module
E             File "master:/Users/dmw/.venv/lib/python2.7/site-packages/mock/mock.py", line 69, in <module>
E               from pbr.version import VersionInfo
E             File "<stdin>", line 220, in load_module
E             File "master:/Users/dmw/.venv/lib/python2.7/site-packages/pbr/version.py", line 25, in <module>
E               import pkg_resources
E             File "<stdin>", line 220, in load_module
E             File "master:/Users/dmw/.venv/lib/python2.7/site-packages/pkg_resources/__init__.py", line 49, in <module>
E               from pkg_resources.extern.six.moves import urllib, map, filter
E             File "<stdin>", line 190, in find_module
E             File "master:/Users/dmw/.venv/lib/python2.7/site-packages/pkg_resources/extern/__init__.py", line 43, in load_module
E               mod = sys.modules[extant]

econtext/master.py:314: CallError
----------------------------------------------------------------------------------- Captured log -----------------------------------------------------------------------------------
master.py                  265 DEBUG    Stream(Context('hostname', 'hostname')).connect()
master.py                   67 DEBUG    create_child() child 41405 fd 12, parent 41402, args ('/Users/dmw/src/econtext/tests/data/fakessh.py', 'hostname', " 'python'", " '-c'", ' \'exec("aW1wb3J0IG9zLHN5cyx6bGliClIsVz1vcy5waXBlKCkKaWYgb3MuZm9yaygpOgoJb3MuZHVwMigwLDEwMCkKCW9zLmR1cDIoUiwwKQoJb3MuY2xvc2UoUikKCW9zLmNsb3NlKFcpCglvcy5leGVjdihzeXMuZXhlY3V0YWJsZSxbJ2Vjb250ZXh0OmRtd0BFbGRpbC5ob21lOjQxNDAyJ10pCmVsc2U6Cglvcy5mZG9wZW4oVywnd2InLDApLndyaXRlKHpsaWIuZGVjb21wcmVzcyhzeXMuc3RkaW4ucmVhZChpbnB1dCgpKSkpCglwcmludCgnT0snKQoJc3lzLmV4aXQoMCk=".decode("base64"))\'')
master.py                  270 DEBUG    Stream(Context('hostname', 'hostname')).connect(): child process stdin/stdout=13
core.py                    679 DEBUG    Broker().register(Context('hostname', 'hostname')) -> r=<Side of Stream(Context('hostname', 'hostname')) fd 13> w=<Side of Stream(Context('hostname', 'hostname')) fd 12>
master.py                  302 DEBUG    Context('hostname', 'hostname').call_with_deadline(None, False, <function log_to_file at 0x1022e6b18>, *('/tmp/log',), **{})
core.py                    516 DEBUG    Context('hostname', 'hostname').enqueue_await_reply(101, None, (False, 'econtext.utils', None, 'log_to_file', ('/tmp/log',), {})) -> reply handle 1000
master.py                  153 DEBUG    ModuleResponder(Context('hostname', 'hostname')).get_module((1000, 'econtext.utils'))
master.py                  100 DEBUG    pkgutil.find_loader('econtext.utils') -> <pkgutil.ImpLoader instance at 0x10236f518>
master.py                  170 DEBUG    _get_module_via_pkgutil found 'econtext.utils': ('/Users/dmw/src/econtext/econtext/utils.py', .., False)
master.py                  153 DEBUG    ModuleResponder(Context('hostname', 'hostname')).get_module((1001, 'econtext.master'))
master.py                  100 DEBUG    pkgutil.find_loader('econtext.master') -> <pkgutil.ImpLoader instance at 0x10236f1b8>
master.py                  170 DEBUG    _get_module_via_pkgutil found 'econtext.master': ('/Users/dmw/src/econtext/econtext/master.py', .., False)
master.py                  302 DEBUG    Context('hostname', 'hostname').call_with_deadline(None, False, <function disable_site_packages at 0x1022b56e0>, *(), **{})
core.py                    516 DEBUG    Context('hostname', 'hostname').enqueue_await_reply(101, None, (False, 'econtext.utils', None, 'disable_site_packages', (), {})) -> reply handle 1001
master.py                   84 DEBUG    econtext: _dispatch_calls((1001, False, 'econtext.utils', None, 'disable_site_packages', (), {}))
master.py                  302 DEBUG    Context('hostname', 'hostname').call_with_deadline(None, False, <function add at 0x1023630c8>, *(1, 2), **{})
core.py                    516 DEBUG    Context('hostname', 'hostname').enqueue_await_reply(101, None, (False, 'ssh_test', None, 'add', (1, 2), {})) -> reply handle 1002
master.py                   84 DEBUG    econtext: _dispatch_calls((1002, False, 'ssh_test', None, 'add', (1, 2), {}))
master.py                   84 DEBUG    econtext: Importer().find_module('ssh_test')
master.py                   84 DEBUG    econtext: find_module('ssh_test') returning self
master.py                   84 DEBUG    econtext: Importer.load_module('ssh_test')
master.py                   84 DEBUG    econtext: Context('master').enqueue_await_reply(100, None, ('ssh_test',)) -> reply handle 1002
master.py                  153 DEBUG    ModuleResponder(Context('hostname', 'hostname')).get_module((1002, 'ssh_test'))
master.py                  100 DEBUG    pkgutil.find_loader('ssh_test') -> <_pytest.assertion.rewrite.AssertionRewritingHook object at 0x10222b5d0>
master.py                  170 DEBUG    _get_module_via_sys_modules found 'ssh_test': ('/Users/dmw/src/econtext/tests/ssh_test.py', .., False)
master.py                   84 DEBUG    econtext: Importer().find_module('unittest')
master.py                   84 DEBUG    econtext: Importer(): 'unittest' is available locally
master.py                   84 DEBUG    econtext: Importer().find_module('econtext.ssh')
master.py                   84 DEBUG    econtext: find_module('econtext.ssh') returning self
master.py                   84 DEBUG    econtext: Importer.load_module('econtext.ssh')
master.py                   84 DEBUG    econtext: Context('master').enqueue_await_reply(100, None, ('econtext.ssh',)) -> reply handle 1003
master.py                  153 DEBUG    ModuleResponder(Context('hostname', 'hostname')).get_module((1003, 'econtext.ssh'))
master.py                  100 DEBUG    pkgutil.find_loader('econtext.ssh') -> <pkgutil.ImpLoader instance at 0x1023662d8>
master.py                  170 DEBUG    _get_module_via_pkgutil found 'econtext.ssh': ('/Users/dmw/src/econtext/econtext/ssh.py', .., False)
master.py                   84 DEBUG    econtext: Importer().find_module('econtext.commands')
master.py                   84 DEBUG    econtext: Importer(): master doesn't know 'econtext.commands'
master.py                   84 DEBUG    econtext: Importer().find_module('commands')
master.py                   84 DEBUG    econtext: Importer(): 'commands' is available locally
master.py                   84 DEBUG    econtext: Importer().find_module('testlib')
master.py                   84 DEBUG    econtext: find_module('testlib') returning self
master.py                   84 DEBUG    econtext: Importer.load_module('testlib')
master.py                   84 DEBUG    econtext: Context('master').enqueue_await_reply(100, None, ('testlib',)) -> reply handle 1004
master.py                  153 DEBUG    ModuleResponder(Context('hostname', 'hostname')).get_module((1004, 'testlib'))
master.py                  100 DEBUG    pkgutil.find_loader('testlib') -> <pkgutil.ImpLoader instance at 0x10235c9e0>
master.py                  170 DEBUG    _get_module_via_pkgutil found 'testlib': ('/Users/dmw/src/econtext/tests/testlib.py', .., False)
master.py                   84 DEBUG    econtext: Importer().find_module('mock')
master.py                   84 DEBUG    econtext: find_module('mock') returning self
master.py                   84 DEBUG    econtext: Importer.load_module('mock')
master.py                   84 DEBUG    econtext: Context('master').enqueue_await_reply(100, None, ('mock',)) -> reply handle 1005
master.py                  153 DEBUG    ModuleResponder(Context('hostname', 'hostname')).get_module((1005, 'mock'))
master.py                  100 DEBUG    pkgutil.find_loader('mock') -> <pkgutil.ImpLoader instance at 0x10235c710>
master.py                  170 DEBUG    _get_module_via_pkgutil found 'mock': ('/Users/dmw/.venv/lib/python2.7/site-packages/mock/__init__.py', .., True)
master.py                  174 DEBUG    get_child_modules('/Users/dmw/.venv/lib/python2.7/site-packages/mock/__init__.py', 'mock') -> ['mock.mock', 'mock.tests']
master.py                   84 DEBUG    econtext: Importer().find_module('mock.mock')
master.py                   84 DEBUG    econtext: find_module('mock.mock') returning self
master.py                   84 DEBUG    econtext: Importer.load_module('mock.mock')
master.py                   84 DEBUG    econtext: Context('master').enqueue_await_reply(100, None, ('mock.mock',)) -> reply handle 1006
master.py                  153 DEBUG    ModuleResponder(Context('hostname', 'hostname')).get_module((1006, 'mock.mock'))
master.py                  100 DEBUG    pkgutil.find_loader('mock.mock') -> <pkgutil.ImpLoader instance at 0x1027a82d8>
master.py                  170 DEBUG    _get_module_via_pkgutil found 'mock.mock': ('/Users/dmw/.venv/lib/python2.7/site-packages/mock/mock.py', .., False)
master.py                   84 DEBUG    econtext: Importer().find_module('builtins')
master.py                   84 DEBUG    econtext: find_module('builtins') returning self
master.py                   84 DEBUG    econtext: Importer.load_module('builtins')
master.py                   84 DEBUG    econtext: Context('master').enqueue_await_reply(100, None, ('builtins',)) -> reply handle 1007
master.py                  153 DEBUG    ModuleResponder(Context('hostname', 'hostname')).get_module((1007, 'builtins'))
master.py                  100 DEBUG    pkgutil.find_loader('builtins') -> None
master.py                  116 DEBUG    'builtins' does not appear in sys.modules
master.py                  182 DEBUG    While importing 'builtins'
Traceback (most recent call last):
  File "/Users/dmw/src/econtext/econtext/master.py", line 167, in get_module
    raise ImportError('could not find %r' % (fullname,))
ImportError: could not find 'builtins'
master.py                   84 DEBUG    econtext: Importer().find_module('six')
master.py                   84 DEBUG    econtext: find_module('six') returning self
master.py                   84 DEBUG    econtext: Importer.load_module('six')
master.py                   84 DEBUG    econtext: Context('master').enqueue_await_reply(100, None, ('six',)) -> reply handle 1008
master.py                  153 DEBUG    ModuleResponder(Context('hostname', 'hostname')).get_module((1008, 'six'))
master.py                  100 DEBUG    pkgutil.find_loader('six') -> <pkgutil.ImpLoader instance at 0x1027a8878>
master.py                  170 DEBUG    _get_module_via_pkgutil found 'six': ('/Users/dmw/.venv/lib/python2.7/site-packages/six.py', .., False)
master.py                   84 DEBUG    econtext: Importer().find_module('pbr')
master.py                   84 DEBUG    econtext: find_module('pbr') returning self
master.py                   84 DEBUG    econtext: Importer.load_module('pbr')
master.py                   84 DEBUG    econtext: Context('master').enqueue_await_reply(100, None, ('pbr',)) -> reply handle 1009
master.py                  153 DEBUG    ModuleResponder(Context('hostname', 'hostname')).get_module((1009, 'pbr'))
master.py                  100 DEBUG    pkgutil.find_loader('pbr') -> <pkgutil.ImpLoader instance at 0x1027a8b00>
master.py                  170 DEBUG    _get_module_via_pkgutil found 'pbr': ('/Users/dmw/.venv/lib/python2.7/site-packages/pbr/__init__.py', .., True)
master.py                  174 DEBUG    get_child_modules('/Users/dmw/.venv/lib/python2.7/site-packages/pbr/__init__.py', 'pbr') -> ['pbr.builddoc', 'pbr.cmd', 'pbr.core', 'pbr.extra_files', 'pbr.find_package', 'pbr.git', 'pbr.hooks', 'pbr.options', 'pbr.packaging', 'pbr.pbr_json', 'pbr.testr_command', 'pbr.tests', 'pbr.util', 'pbr.version']
master.py                   84 DEBUG    econtext: Importer().find_module('pbr.version')
master.py                   84 DEBUG    econtext: find_module('pbr.version') returning self
master.py                   84 DEBUG    econtext: Importer.load_module('pbr.version')
master.py                   84 DEBUG    econtext: Context('master').enqueue_await_reply(100, None, ('pbr.version',)) -> reply handle 1010
master.py                  153 DEBUG    ModuleResponder(Context('hostname', 'hostname')).get_module((1010, 'pbr.version'))
master.py                  100 DEBUG    pkgutil.find_loader('pbr.version') -> <pkgutil.ImpLoader instance at 0x1027b1128>
master.py                  170 DEBUG    _get_module_via_pkgutil found 'pbr.version': ('/Users/dmw/.venv/lib/python2.7/site-packages/pbr/version.py', .., False)
master.py                   84 DEBUG    econtext: Importer().find_module('pbr.itertools')
master.py                   84 DEBUG    econtext: Importer(): master doesn't know 'pbr.itertools'
master.py                   84 DEBUG    econtext: Importer().find_module('pbr.operator')
master.py                   84 DEBUG    econtext: Importer(): master doesn't know 'pbr.operator'
master.py                   84 DEBUG    econtext: Importer().find_module('pbr.sys')
master.py                   84 DEBUG    econtext: Importer(): master doesn't know 'pbr.sys'
master.py                   84 DEBUG    econtext: Importer().find_module('pbr.pkg_resources')
master.py                   84 DEBUG    econtext: Importer(): master doesn't know 'pbr.pkg_resources'
master.py                   84 DEBUG    econtext: Importer().find_module('pkg_resources')
master.py                   84 DEBUG    econtext: find_module('pkg_resources') returning self
master.py                   84 DEBUG    econtext: Importer.load_module('pkg_resources')
master.py                   84 DEBUG    econtext: Context('master').enqueue_await_reply(100, None, ('pkg_resources',)) -> reply handle 1011
master.py                  153 DEBUG    ModuleResponder(Context('hostname', 'hostname')).get_module((1011, 'pkg_resources'))
master.py                  100 DEBUG    pkgutil.find_loader('pkg_resources') -> <pkgutil.ImpLoader instance at 0x1027b1248>
master.py                  170 DEBUG    _get_module_via_pkgutil found 'pkg_resources': ('/Users/dmw/.venv/lib/python2.7/site-packages/pkg_resources/__init__.py', .., True)
master.py                  174 DEBUG    get_child_modules('/Users/dmw/.venv/lib/python2.7/site-packages/pkg_resources/__init__.py', 'pkg_resources') -> ['pkg_resources._vendor', 'pkg_resources.extern']
master.py                   84 DEBUG    econtext: Importer().find_module('io')
master.py                   84 DEBUG    econtext: Importer(): 'io' is available locally
master.py                   84 DEBUG    econtext: Importer().find_module('zipfile')
master.py                   84 DEBUG    econtext: Importer(): 'zipfile' is available locally
master.py                   84 DEBUG    econtext: Importer().find_module('symbol')
master.py                   84 DEBUG    econtext: Importer(): 'symbol' is available locally
master.py                   84 DEBUG    econtext: Importer().find_module('platform')
master.py                   84 DEBUG    econtext: Importer(): 'platform' is available locally
master.py                   84 DEBUG    econtext: Importer().find_module('plistlib')
master.py                   84 DEBUG    econtext: Importer(): 'plistlib' is available locally
master.py                   84 DEBUG    econtext: Importer().find_module('email')
master.py                   84 DEBUG    econtext: Importer(): 'email' is available locally
master.py                   84 DEBUG    econtext: Importer().find_module('email.parser')
master.py                   84 DEBUG    econtext: Importer(): 'email.parser' is submodule of a package we did not load
master.py                   84 DEBUG    econtext: Importer().find_module('email.warnings')
master.py                   84 DEBUG    econtext: Importer(): 'email.warnings' is submodule of a package we did not load
master.py                   84 DEBUG    econtext: Importer().find_module('email.cStringIO')
master.py                   84 DEBUG    econtext: Importer(): 'email.cStringIO' is submodule of a package we did not load
master.py                   84 DEBUG    econtext: Importer().find_module('email.feedparser')
master.py                   84 DEBUG    econtext: Importer(): 'email.feedparser' is submodule of a package we did not load
master.py                   84 DEBUG    econtext: Importer().find_module('email.re')
master.py                   84 DEBUG    econtext: Importer(): 'email.re' is submodule of a package we did not load
master.py                   84 DEBUG    econtext: Importer().find_module('email.errors')
master.py                   84 DEBUG    econtext: Importer(): 'email.errors' is submodule of a package we did not load
master.py                   84 DEBUG    econtext: Importer().find_module('email.message')
master.py                   84 DEBUG    econtext: Importer(): 'email.message' is submodule of a package we did not load
master.py                   84 DEBUG    econtext: Importer().find_module('email.uu')
master.py                   84 DEBUG    econtext: Importer(): 'email.uu' is submodule of a package we did not load
master.py                   84 DEBUG    econtext: Importer().find_module('uu')
master.py                   84 DEBUG    econtext: Importer(): 'uu' is available locally
master.py                   84 DEBUG    econtext: Importer().find_module('email.binascii')
master.py                   84 DEBUG    econtext: Importer(): 'email.binascii' is submodule of a package we did not load
master.py                   84 DEBUG    econtext: Importer().find_module('email.charset')
master.py                   84 DEBUG    econtext: Importer(): 'email.charset' is submodule of a package we did not load
master.py                   84 DEBUG    econtext: Importer().find_module('email.codecs')
master.py                   84 DEBUG    econtext: Importer(): 'email.codecs' is submodule of a package we did not load
master.py                   84 DEBUG    econtext: Importer().find_module('email.base64mime')
master.py                   84 DEBUG    econtext: Importer(): 'email.base64mime' is submodule of a package we did not load
master.py                   84 DEBUG    econtext: Importer().find_module('email.utils')
master.py                   84 DEBUG    econtext: Importer(): 'email.utils' is submodule of a package we did not load
master.py                   84 DEBUG    econtext: Importer().find_module('email.os')
master.py                   84 DEBUG    econtext: Importer(): 'email.os' is submodule of a package we did not load
master.py                   84 DEBUG    econtext: Importer().find_module('email.time')
master.py                   84 DEBUG    econtext: Importer(): 'email.time' is submodule of a package we did not load
master.py                   84 DEBUG    econtext: Importer().find_module('email.base64')
master.py                   84 DEBUG    econtext: Importer(): 'email.base64' is submodule of a package we did not load
master.py                   84 DEBUG    econtext: Importer().find_module('base64')
master.py                   84 DEBUG    econtext: Importer(): 'base64' is available locally
master.py                   84 DEBUG    econtext: Importer().find_module('email.random')
master.py                   84 DEBUG    econtext: Importer(): 'email.random' is submodule of a package we did not load
master.py                   84 DEBUG    econtext: Importer().find_module('email.socket')
master.py                   84 DEBUG    econtext: Importer(): 'email.socket' is submodule of a package we did not load
master.py                   84 DEBUG    econtext: Importer().find_module('email.urllib')
master.py                   84 DEBUG    econtext: Importer(): 'email.urllib' is submodule of a package we did not load
master.py                   84 DEBUG    econtext: Importer().find_module('urllib')
master.py                   84 DEBUG    econtext: Importer(): 'urllib' is available locally
master.py                   84 DEBUG    econtext: Importer().find_module('email._parseaddr')
master.py                   84 DEBUG    econtext: Importer(): 'email._parseaddr' is submodule of a package we did not load
master.py                   84 DEBUG    econtext: Importer().find_module('email.calendar')
master.py                   84 DEBUG    econtext: Importer(): 'email.calendar' is submodule of a package we did not load
master.py                   84 DEBUG    econtext: Importer().find_module('calendar')
master.py                   84 DEBUG    econtext: Importer(): 'calendar' is available locally
master.py                   84 DEBUG    econtext: Importer().find_module('email.quopri')
master.py                   84 DEBUG    econtext: Importer(): 'email.quopri' is submodule of a package we did not load
master.py                   84 DEBUG    econtext: Importer().find_module('quopri')
master.py                   84 DEBUG    econtext: Importer(): 'quopri' is available locally
master.py                   84 DEBUG    econtext: Importer().find_module('email.encoders')
master.py                   84 DEBUG    econtext: Importer(): 'email.encoders' is submodule of a package we did not load
master.py                   84 DEBUG    econtext: Importer().find_module('email.quoprimime')
master.py                   84 DEBUG    econtext: Importer(): 'email.quoprimime' is submodule of a package we did not load
master.py                   84 DEBUG    econtext: Importer().find_module('email.string')
master.py                   84 DEBUG    econtext: Importer(): 'email.string' is submodule of a package we did not load
master.py                   84 DEBUG    econtext: Importer().find_module('email.iterators')
master.py                   84 DEBUG    econtext: Importer(): 'email.iterators' is submodule of a package we did not load
master.py                   84 DEBUG    econtext: Importer().find_module('tempfile')
master.py                   84 DEBUG    econtext: Importer(): 'tempfile' is available locally
master.py                   84 DEBUG    econtext: Importer().find_module('_imp')
master.py                   84 DEBUG    econtext: find_module('_imp') returning self
master.py                   84 DEBUG    econtext: Importer.load_module('_imp')
master.py                   84 DEBUG    econtext: Context('master').enqueue_await_reply(100, None, ('_imp',)) -> reply handle 1012
master.py                  153 DEBUG    ModuleResponder(Context('hostname', 'hostname')).get_module((1012, '_imp'))
master.py                  100 DEBUG    pkgutil.find_loader('_imp') -> None
master.py                  116 DEBUG    '_imp' does not appear in sys.modules
master.py                  182 DEBUG    While importing '_imp'
Traceback (most recent call last):
  File "/Users/dmw/src/econtext/econtext/master.py", line 167, in get_module
    raise ImportError('could not find %r' % (fullname,))
ImportError: could not find '_imp'
master.py                   84 DEBUG    econtext: Importer().find_module('pkg_resources.extern')
master.py                   84 DEBUG    econtext: find_module('pkg_resources.extern') returning self
master.py                   84 DEBUG    econtext: Importer.load_module('pkg_resources.extern')
master.py                   84 DEBUG    econtext: Context('master').enqueue_await_reply(100, None, ('pkg_resources.extern',)) -> reply handle 1013
master.py                  153 DEBUG    ModuleResponder(Context('hostname', 'hostname')).get_module((1013, 'pkg_resources.extern'))
master.py                  100 DEBUG    pkgutil.find_loader('pkg_resources.extern') -> <pkgutil.ImpLoader instance at 0x1027c7290>
master.py                  170 DEBUG    _get_module_via_pkgutil found 'pkg_resources.extern': ('/Users/dmw/.venv/lib/python2.7/site-packages/pkg_resources/extern/__init__.py', .., True)
master.py                  174 DEBUG    get_child_modules('/Users/dmw/.venv/lib/python2.7/site-packages/pkg_resources/extern/__init__.py', 'pkg_resources.extern') -> []
master.py                   84 DEBUG    econtext: Importer().find_module('pkg_resources.extern.sys')
master.py                   84 DEBUG    econtext: Importer(): master doesn't know 'pkg_resources.extern.sys'
master.py                   84 DEBUG    econtext: Importer().find_module('pkg_resources.extern.six')
master.py                   84 DEBUG    econtext: Importer(): master doesn't know 'pkg_resources.extern.six'
master.py                   84 DEBUG    econtext: Importer().find_module('pkg_resources._vendor')
master.py                   84 DEBUG    econtext: find_module('pkg_resources._vendor') returning self
master.py                   84 DEBUG    econtext: Importer.load_module('pkg_resources._vendor')
master.py                   84 DEBUG    econtext: Context('master').enqueue_await_reply(100, None, ('pkg_resources._vendor',)) -> reply handle 1014
master.py                  153 DEBUG    ModuleResponder(Context('hostname', 'hostname')).get_module((1014, 'pkg_resources._vendor'))
master.py                  100 DEBUG    pkgutil.find_loader('pkg_resources._vendor') -> <pkgutil.ImpLoader instance at 0x1027c7680>
master.py                  170 DEBUG    _get_module_via_pkgutil found 'pkg_resources._vendor': ('/Users/dmw/.venv/lib/python2.7/site-packages/pkg_resources/_vendor/__init__.py', .., True)
master.py                  174 DEBUG    get_child_modules('/Users/dmw/.venv/lib/python2.7/site-packages/pkg_resources/_vendor/__init__.py', 'pkg_resources._vendor') -> ['pkg_resources._vendor.packaging', 'pkg_resources._vendor.six']
master.py                   84 DEBUG    econtext: Importer().find_module('pkg_resources._vendor.six')
master.py                   84 DEBUG    econtext: find_module('pkg_resources._vendor.six') returning self
master.py                   84 DEBUG    econtext: Importer.load_module('pkg_resources._vendor.six')
master.py                   84 DEBUG    econtext: Context('master').enqueue_await_reply(100, None, ('pkg_resources._vendor.six',)) -> reply handle 1015
master.py                  153 DEBUG    ModuleResponder(Context('hostname', 'hostname')).get_module((1015, 'pkg_resources._vendor.six'))
master.py                  100 DEBUG    pkgutil.find_loader('pkg_resources._vendor.six') -> <pkgutil.ImpLoader instance at 0x1027c73f8>
master.py                  170 DEBUG    _get_module_via_pkgutil found 'pkg_resources._vendor.six': ('/Users/dmw/.venv/lib/python2.7/site-packages/pkg_resources/_vendor/six.py', .., False)
master.py                   84 DEBUG    econtext: Importer().find_module('pkg_resources.extern.six.moves')
core.py                    760 DEBUG    Broker().shutdown()
master.py                  202 DEBUG    Stream(Context('hostname', 'hostname')) closing CALL_FUNCTION channel
core.py                    337 DEBUG    Waker(Broker()).on_shutdown()
core.py                    330 DEBUG    Waker(Broker()).on_disconnect()
master.py                   84 DEBUG    econtext: Waker(Broker()).on_shutdown()
master.py                   84 DEBUG    econtext: Waker(Broker()).on_disconnect()
master.py                   84 DEBUG    econtext: <IoLogger stderr>.on_shutdown()
master.py                   84 DEBUG    econtext: <IoLogger stdout>.on_shutdown()
master.py                   84 DEBUG    econtext: Stream(Context('master')).on_shutdown(Broker())
master.py                   84 DEBUG    econtext: ExternalContext.main() normal exit
master.py                   84 DEBUG    econtext: Broker().shutdown()
master.py                   84 DEBUG    econtext: <IoLogger stdout>.on_receive()
master.py                   84 DEBUG    econtext: <IoLogger stdout>.on_disconnect()
master.py                   84 DEBUG    econtext: <IoLogger stderr>.on_receive()
master.py                   84 DEBUG    econtext: <IoLogger stderr>.on_disconnect()
core.py                    330 DEBUG    Stream(Context('hostname', 'hostname')).on_disconnect()
core.py                    486 DEBUG    Context('hostname', 'hostname').on_shutdown(Broker())
core.py                    488 DEBUG    Context('hostname', 'hostname').on_disconnect(): killing 100: <bound method ModuleResponder.get_module of ModuleResponder(Context('hostname', 'hostname'))>
master.py                  153 DEBUG    ModuleResponder(Context('hostname', 'hostname')).get_module(<Dead>)
core.py                    488 DEBUG    Context('hostname', 'hostname').on_disconnect(): killing 102: <bound method LogForwarder.forward_log of <econtext.master.LogForwarder object at 0x10236a750>>
------------------------------------------------------------------------------ Captured stdout setup -------------------------------------------------------------------------------
[<TestCaseFunction 'test_okay'>]
=================================================================== 1 failed, 1 pytest-warnings in 0.57 seconds ====================================================================
[22:43:16 Eldil!8 econtext] n