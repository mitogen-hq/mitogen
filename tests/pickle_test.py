from mitogen.core import BytesIO
from mitogen.core import Pickler
from mitogen.core import Unpickler
from mitogen.core import UnpicklingError

import testlib

def dumps(obj, protocol):
    f = BytesIO()
    Pickler(f, protocol).dump(obj)
    return f.getvalue()


def find_complex(module, func):
    if (module, func) == ('__builtin__', 'complex'): return complex
    raise UnpicklingError


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
