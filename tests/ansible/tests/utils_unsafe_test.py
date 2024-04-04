import unittest

from ansible.utils.unsafe_proxy import AnsibleUnsafeBytes
from ansible.utils.unsafe_proxy import AnsibleUnsafeText
from ansible.utils.unsafe_proxy import wrap_var

import ansible_mitogen.utils.unsafe

import mitogen.core


class Bytes(bytes): pass
class Dict(dict): pass
class List(list): pass
class Set(set): pass
class Text(mitogen.core.UnicodeType): pass
class Tuple(tuple): pass


class CastTest(unittest.TestCase):
    def assertIsType(self, obj, cls, msg=None):
        self.assertIs(type(obj), cls, msg)

    def assertUnchanged(self, obj):
        self.assertIs(ansible_mitogen.utils.unsafe.cast(obj), obj)

    def assertCasts(self, obj, expected):
        cast = ansible_mitogen.utils.unsafe.cast
        self.assertEqual(cast(obj), expected)
        self.assertIsType(cast(obj), type(expected))

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
        self.assertCasts(wrap_var(()), [])
        
    def test_subtypes_roundtrip(self):
        self.assertCasts(wrap_var(Bytes()), b'')
        self.assertCasts(wrap_var(Dict()), {})
        self.assertCasts(wrap_var(List()), [])
        self.assertCasts(wrap_var(Text()), u'')
        self.assertCasts(wrap_var(Tuple()), [])

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

    def test_subtype_roundtrip_tuple(self):
        # wrap_var() preserves sequence types, cast() does not (for now)
        obj = Tuple([Tuple([u'abc'])])
        wrapped = wrap_var(obj)
        unwrapped = ansible_mitogen.utils.unsafe.cast(wrapped)
        self.assertEqual(unwrapped, [[u'abc']])
        self.assertIsType(unwrapped, list)
        self.assertIsType(unwrapped[0], list)
        self.assertIsType(unwrapped[0][0], mitogen.core.UnicodeType)

    def test_unknown_types_raise(self):
        cast = ansible_mitogen.utils.unsafe.cast
        self.assertRaises(TypeError, cast, set())
        self.assertRaises(TypeError, cast, Set())
        self.assertRaises(TypeError, cast, 4j)
