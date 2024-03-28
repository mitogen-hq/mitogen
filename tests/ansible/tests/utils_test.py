import unittest

import ansible.utils.unsafe_proxy

import ansible_mitogen.utils
import ansible_mitogen.utils.unsafe
import mitogen.core


class AnsibleVersionTest(unittest.TestCase):
    def test_ansible_version(self):
        self.assertIsInstance(ansible_mitogen.utils.ansible_version, tuple)
        self.assertIsInstance(ansible_mitogen.utils.ansible_version[0], int)
        self.assertIsInstance(ansible_mitogen.utils.ansible_version[1], int)
        self.assertEqual(2, ansible_mitogen.utils.ansible_version[0])


class Bytes(bytes): pass
class Dict(dict): pass
class Frozenset(frozenset): pass
class List(list): pass
class Set(set): pass
class Tuple(tuple): pass
class Unicode(mitogen.core.UnicodeType): pass


class UnwrapUnsafeTest(unittest.TestCase):
    def assertIsType(self, obj, cls, msg=None):
        self.assertIs(type(obj), cls, msg)

    def assertUnchanged(self, v):
        unwrapped = ansible_mitogen.utils.unsafe.unwrap_var(v)
        self.assertIs(unwrapped, v)

    def assertUnwraps(self, v, expected_type):
        wrapped = ansible.utils.unsafe_proxy.wrap_var(v)
        unwrapped = ansible_mitogen.utils.unsafe.unwrap_var(wrapped)
        self.assertEqual(unwrapped, wrapped)
        self.assertIsType(unwrapped, expected_type)

    def test_ansible_unsafe(self):
        self.assertUnwraps(b'abc', expected_type=bytes)
        self.assertUnwraps(u'abc', expected_type=mitogen.core.UnicodeType)

    def test_ansible_unsafe_nested(self):
        self.assertUnwraps(b'abc', expected_type=bytes)
        self.assertUnwraps(u'abc', expected_type=mitogen.core.UnicodeType)

    def test_builtins_passthrough(self):
        self.assertUnchanged(0)
        self.assertUnchanged(0.0)
        self.assertUnchanged(0+0j)
        self.assertUnchanged(False)
        self.assertUnchanged(True)
        self.assertUnchanged(None)
        self.assertUnchanged(b'')
        self.assertUnchanged(u'')
        self.assertUnchanged(mitogen.core.long(0))

    def test_builtins_roundtrip(self):
        self.assertUnwraps({}, expected_type=dict)
        self.assertUnwraps([], expected_type=list)
        self.assertUnwraps((), expected_type=tuple)
        self.assertUnwraps(set(), expected_type=set)

    def test_subtypes_roundtrip(self):
        self.assertUnwraps(Bytes(), expected_type=bytes)
        self.assertUnwraps(Dict(), expected_type=dict)
        self.assertUnwraps(Frozenset(), expected_type=set)
        self.assertUnwraps(List(), expected_type=List)  # Mirrors wrap_var()
        self.assertUnwraps(Set(), expected_type=set)
        self.assertUnwraps(Tuple(), expected_type=Tuple)  # Mirrors wrap_var()
        self.assertUnwraps(Unicode(), expected_type=mitogen.core.UnicodeType)

    def test_subtype_roundtrip_dict(self):
        # wrap_var() doesn't preserve mapping types
        v = Dict(foo=Dict(bar=u'abc'))
        wrapped = ansible.utils.unsafe_proxy.wrap_var(v)
        unwrapped = ansible_mitogen.utils.unsafe.unwrap_var(wrapped)
        self.assertEqual(unwrapped, wrapped)
        self.assertIsType(unwrapped, dict)
        self.assertIsType(unwrapped['foo'], dict)
        self.assertIsType(unwrapped['foo']['bar'], mitogen.core.UnicodeType)

    def test_subtype_roundtrip_list(self):
        # wrap_var() preserves sequence types
        v = List([List([u'abc'])])
        wrapped = ansible.utils.unsafe_proxy.wrap_var(v)
        unwrapped = ansible_mitogen.utils.unsafe.unwrap_var(wrapped)
        self.assertEqual(unwrapped, wrapped)
        self.assertIsType(unwrapped, List)
        self.assertIsType(unwrapped[0], List)
        self.assertIsType(unwrapped[0][0], mitogen.core.UnicodeType)

    def test_subtype_roundtrip_tuple(self):
        # wrap_var() preserves sequence types
        v = Tuple([Tuple([u'abc'])])
        wrapped = ansible.utils.unsafe_proxy.wrap_var(v)
        unwrapped = ansible_mitogen.utils.unsafe.unwrap_var(wrapped)
        self.assertEqual(unwrapped, wrapped)
        self.assertIsType(unwrapped, Tuple)
        self.assertIsType(unwrapped[0], Tuple)
        self.assertIsType(unwrapped[0][0], mitogen.core.UnicodeType)
