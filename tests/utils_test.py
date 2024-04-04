import mitogen.core
import mitogen.master
import mitogen.utils
from mitogen.core import b

import testlib


def func0(router):
    return router


@mitogen.utils.with_router
def func(router):
    "Docstring of func"
    return router


class RunWithRouterTest(testlib.TestCase):
    # test_shutdown_on_exception
    # test_shutdown_on_success

    def test_run_with_broker(self):
        router = mitogen.utils.run_with_router(func0)
        self.assertIsInstance(router, mitogen.master.Router)
        self.assertFalse(testlib.threading__thread_is_alive(router.broker._thread))


class WithRouterTest(testlib.TestCase):
    def test_with_broker(self):
        router = func()
        self.assertIsInstance(router, mitogen.master.Router)
        self.assertFalse(testlib.threading__thread_is_alive(router.broker._thread))

    def test_with_broker_preserves_attributes(self):
        self.assertEqual(func.__doc__, 'Docstring of func')
        self.assertEqual(func.__name__, 'func')


class Dict(dict): pass
class List(list): pass
class Tuple(tuple): pass
class Unicode(mitogen.core.UnicodeType): pass
class Bytes(mitogen.core.BytesType): pass


class StubbornBytes(mitogen.core.BytesType):
    """
    A binary string type that persists through `bytes(...)`.

    Stand-in for `AnsibleUnsafeBytes()` in Ansible 7-9 (core 2.14-2.16), after
    fixes/mitigations for CVE-2023-5764.
    """
    if mitogen.core.PY3:
        def __bytes__(self): return self
        def __str__(self): return self.decode()
    else:
        def __str__(self): return self
        def __unicode__(self): return self.decode()

    def decode(self, encoding='utf-8', errors='strict'):
        s = super(StubbornBytes).encode(encoding=encoding, errors=errors)
        return StubbornText(s)


class StubbornText(mitogen.core.UnicodeType):
    """
    A text string type that persists through `unicode(...)` or `str(...)`.

    Stand-in for `AnsibleUnsafeText()` in Ansible 7-9 (core 2.14-2.16), after
    following fixes/mitigations for CVE-2023-5764.
    """
    if mitogen.core.PY3:
        def __bytes__(self): return self.encode()
        def __str__(self): return self
    else:
        def __str__(self): return self.encode()
        def __unicode__(self): return self

    def encode(self, encoding='utf-8', errors='strict'):
        s = super(StubbornText).encode(encoding=encoding, errors=errors)
        return StubbornBytes(s)


class CastTest(testlib.TestCase):
    def test_dict(self):
        self.assertEqual(type(mitogen.utils.cast({})), dict)
        self.assertEqual(type(mitogen.utils.cast(Dict())), dict)

    def test_nested_dict(self):
        specimen = mitogen.utils.cast(Dict({'k': Dict({'k2': 'v2'})}))
        self.assertEqual(type(specimen), dict)
        self.assertEqual(type(specimen['k']), dict)

    def test_list(self):
        self.assertEqual(type(mitogen.utils.cast([])), list)
        self.assertEqual(type(mitogen.utils.cast(List())), list)

    def test_nested_list(self):
        specimen = mitogen.utils.cast(List((0, 1, List((None,)))))
        self.assertEqual(type(specimen), list)
        self.assertEqual(type(specimen[2]), list)

    def test_tuple(self):
        self.assertEqual(type(mitogen.utils.cast(())), list)
        self.assertEqual(type(mitogen.utils.cast(Tuple())), list)

    def test_nested_tuple(self):
        specimen = mitogen.utils.cast(Tuple((0, 1, Tuple((None,)))))
        self.assertEqual(type(specimen), list)
        self.assertEqual(type(specimen[2]), list)

    def assertUnchanged(self, v):
        self.assertIs(mitogen.utils.cast(v), v)

    def test_passthrough(self):
        self.assertUnchanged(0)
        self.assertUnchanged(0.0)
        self.assertUnchanged(float('inf'))
        self.assertUnchanged(True)
        self.assertUnchanged(False)
        self.assertUnchanged(None)

    def test_unicode(self):
        self.assertEqual(type(mitogen.utils.cast(u'')), mitogen.core.UnicodeType)
        self.assertEqual(type(mitogen.utils.cast(Unicode())), mitogen.core.UnicodeType)

    def test_bytes(self):
        self.assertEqual(type(mitogen.utils.cast(b(''))), mitogen.core.BytesType)
        self.assertEqual(type(mitogen.utils.cast(Bytes())), mitogen.core.BytesType)

    def test_stubborn_types_raise(self):
        stubborn_bytes = StubbornBytes(b('abc'))
        self.assertIs(stubborn_bytes, mitogen.core.BytesType(stubborn_bytes))
        self.assertRaises(TypeError, mitogen.utils.cast, stubborn_bytes)

        stubborn_text = StubbornText(u'abc')
        self.assertIs(stubborn_text, mitogen.core.UnicodeType(stubborn_text))
        self.assertRaises(TypeError, mitogen.utils.cast, stubborn_text)

    def test_unknown(self):
        self.assertRaises(TypeError, mitogen.utils.cast, set())
        self.assertRaises(TypeError, mitogen.utils.cast, 4j)
