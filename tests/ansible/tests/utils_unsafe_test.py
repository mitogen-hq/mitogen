import unittest

from ansible.utils.unsafe_proxy import AnsibleUnsafeBytes
from ansible.utils.unsafe_proxy import AnsibleUnsafeText
from ansible.utils.unsafe_proxy import wrap_var

import ansible_mitogen.utils
import ansible_mitogen.utils.unsafe

import mitogen.core


class Bytes(bytes): pass
class Dict(dict): pass
class List(list): pass
class Set(set): pass
class Text(mitogen.core.UnicodeType): pass
class Tuple(tuple): pass


class CastMixin(unittest.TestCase):
    def assertIsType(self, obj, cls, msg=None):
        self.assertIs(type(obj), cls, msg)

    def assertUnchanged(self, obj):
        self.assertIs(ansible_mitogen.utils.unsafe.cast(obj), obj)

    def assertCasts(self, obj, expected):
        cast = ansible_mitogen.utils.unsafe.cast
        self.assertEqual(cast(obj), expected)
        self.assertIsType(cast(obj), type(expected))


class CastKnownTest(CastMixin):
    def test_ansible_unsafe(self):
        self.assertCasts(AnsibleUnsafeBytes(b'abc'), b'abc')
        self.assertCasts(AnsibleUnsafeText(u'abc'), u'abc')

    def test_passthrough(self):
        self.assertUnchanged(0)
        self.assertUnchanged(0.0)
        self.assertUnchanged(False)
        self.assertUnchanged(True)
        self.assertUnchanged(None)
        self.assertUnchanged(b'')
        self.assertUnchanged(u'')

    def test_builtins_roundtrip(self):
        self.assertCasts(wrap_var(b''), b'')
        self.assertCasts(wrap_var({}), {})
        self.assertCasts(wrap_var([]), [])
        self.assertCasts(wrap_var(u''), u'')

    def test_subtypes_roundtrip(self):
        self.assertCasts(wrap_var(Bytes()), b'')
        self.assertCasts(wrap_var(Dict()), {})
        self.assertCasts(wrap_var(List()), [])
        self.assertCasts(wrap_var(Text()), u'')

    def test_subtype_nested_dict(self):
        obj = Dict(foo=Dict(bar=u'abc'))
        wrapped = wrap_var(obj)
        unwrapped = ansible_mitogen.utils.unsafe.cast(wrapped)
        self.assertEqual(unwrapped, {'foo': {'bar': u'abc'}})
        self.assertIsType(unwrapped, dict)
        self.assertIsType(unwrapped['foo'], dict)
        self.assertIsType(unwrapped['foo']['bar'], mitogen.core.UnicodeType)

    def test_subtype_roundtrip_list(self):
        # wrap_var() preserves sequence types, cast() does not (for now)
        obj = List([List([u'abc'])])
        wrapped = wrap_var(obj)
        unwrapped = ansible_mitogen.utils.unsafe.cast(wrapped)
        self.assertEqual(unwrapped, [[u'abc']])
        self.assertIsType(unwrapped, list)
        self.assertIsType(unwrapped[0], list)
        self.assertIsType(unwrapped[0][0], mitogen.core.UnicodeType)


@unittest.skipIf(
    ansible_mitogen.utils.ansible_version[:2] <= (2, 18),
    'Ansible <= 11 (ansible-core >= 2.18) does not send/receive sets',
)
class CastSetTest(CastMixin):
    def test_set(self):
        self.assertCasts(wrap_var(set()), set())

    def test_set_subclass(self):
        self.assertCasts(wrap_var(Set()), set())


class CastTupleTest(CastMixin):
    def test_tuple(self):
        if ansible_mitogen.utils.ansible_version[:2] >= (2, 19):
            expected = ()
        else:
            expected = []
        self.assertCasts(wrap_var(Tuple()), expected)

    def test_tuple_subclass(self):
        if ansible_mitogen.utils.ansible_version[:2] >= (2, 19):
            expected = ()
        else:
            expected = []
        self.assertCasts(wrap_var(()), expected)

    def test_tuple_subclass_with_contents(self):
        if ansible_mitogen.utils.ansible_version[:2] >= (2, 19):
            expected = ((u'abc',),)
        else:
            expected = [[u'abc']]

        obj = Tuple([Tuple([u'abc'])])
        wrapped = wrap_var(obj)
        unwrapped = ansible_mitogen.utils.unsafe.cast(wrapped)
        self.assertEqual(unwrapped, expected)
        self.assertIsType(unwrapped, type(expected))
        self.assertIsType(unwrapped[0], type(expected[0]))
        self.assertIsType(unwrapped[0][0], mitogen.core.UnicodeType)


class CastUknownTypeTest(unittest.TestCase):
    @unittest.skipIf(
        ansible_mitogen.utils.ansible_version[:2] >= (2, 19),
        'Ansible >= 12 (ansible-core >= 2.19) uses/preserves sets',
    )
    def test_set_raises(self):
        cast = ansible_mitogen.utils.unsafe.cast
        self.assertRaises(TypeError, cast, set())
        self.assertRaises(TypeError, cast, Set())

    def test_complex_raises(self):
        cast = ansible_mitogen.utils.unsafe.cast
        self.assertRaises(TypeError, cast, 4j)
