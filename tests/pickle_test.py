from mitogen.core import BytesIO
from mitogen.core import BytesType
from mitogen.core import Pickler
from mitogen.core import Unpickler
from mitogen.core import UnicodeType
from mitogen.core import UnpicklingError
from mitogen.core import b
from mitogen.core import find_deny

import testlib

def dumps(obj, protocol):
    f = BytesIO()
    Pickler(f, protocol).dump(obj)
    return f.getvalue()


def loads(s, find_class):
    return Unpickler(BytesIO(s), find_class).load()


def find_bytes(module, func):
    lookup = {
        ('__builtin__', 'bytes'): BytesType,
        ('_codecs', 'encode'): UnicodeType.encode,
    }
    try:
        return lookup[(module, func)]
    except KeyError:
        raise UnpicklingError


def find_complex(module, func):
    if (module, func) == ('__builtin__', 'complex'): return complex
    raise UnpicklingError


class PicklerTest(testlib.TestCase):
    def test_bytes_toplevel(self):
        pickled = dumps(b('abc'), protocol=2)
        self.assertFalse(b('_codecs') in pickled)
        self.assertFalse(b('encode') in pickled)
        self.assertFalse(b('latin1') in pickled)


class RoundTripTest(testlib.TestCase):
    def assertRoundTrip(self, obj, find_class):
        self.assertEqual(obj, loads(dumps(obj, protocol=2), find_class))

    def test_bytes(self):
        # Top level bytes should not invoke _codecs.decode
        self.assertRoundTrip(b(''), find_deny)
        self.assertRoundTrip(b('abc'), find_deny)

        # Nested bytes still (unavoidably) invokes _codecs.decode
        self.assertRoundTrip([b('')], find_bytes)
        self.assertRoundTrip([b('abc')], find_bytes)


class UnpicklerTest(testlib.TestCase):
    # These types have no dedicated pickle opcodes at this protocol, they use
    # GLOBAL which invokes find_global() or find_class() during unpickling.
    pickled_complex = dumps(1j, protocol=2)
    pickled_frozenset = dumps(frozenset([1]), protocol=2)

    def test_default_denies(self):
        unpickler = Unpickler(BytesIO(self.pickled_complex))
        self.assertRaises(UnpicklingError, unpickler.load)

    def test_explicit_callback_allows(self):
        unpickler = Unpickler(BytesIO(self.pickled_complex), find_complex)
        self.assertEqual(1j, unpickler.load())

    def test_explicit_callback_denies(self):
        unpickler = Unpickler(BytesIO(self.pickled_frozenset), find_complex)
        self.assertRaises(UnpicklingError, unpickler.load)
