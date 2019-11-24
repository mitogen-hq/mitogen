
from mitogen.core import encode
from mitogen.core import decode

from mitogen.core import *

assert KIND_TRUE == encode(True)
assert True is decode(encode(True))

assert KIND_FALSE == encode(False)
assert False is decode(encode(False))

assert KIND_NONE == encode(None)
assert None is decode(encode(None))

assert -(2**32-1) == decode(encode(-(2**32-1)))
assert (2**32-1) == decode(encode(2**32-1))
assert -(2**64-1) == decode(encode(-(2**64-1)))
assert (2**64-1) == decode(encode(2**64-1))
assert u'\N{snowman}' == decode(encode(u'\N{snowman}'))
assert b'snowman' == decode(encode(b'snowman'))
assert [] == decode(encode([]))
assert [False, True] == decode(encode([False, True]))
assert (False, True) == decode(encode((False, True)))
assert set([False, True]) == decode(encode(set([False, True])))
assert {'a': 0, 'b': 1} == decode(encode({'a': 0, 'b': 1}))

assert type(decode(encode(Blob(b('dave'))))) is Blob
assert type(decode(encode(Secret('dave')))) is Secret

assert type(decode(encode(Kwargs({})))) is Kwargs
assert Kwargs({'a': 1}) == decode(encode(Kwargs({'a': 1})))

assert 1 == decode(encode(Context(None, 1))).context_id
b = Broker()
r = Router(b)
try:
    assert 1234 == decode(encode(Sender(Context(r, 1), 1234)), r).dst_handle
finally:
    b.shutdown()
