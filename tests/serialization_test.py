
import pickle
import unittest2

import mitogen.core
from mitogen.core import b

import testlib


class EvilObject(object):
    pass


def roundtrip(v):
    msg = mitogen.core.Message.pickled(v)
    return mitogen.core.Message(data=msg.data).unpickle()


class EvilObjectTest(testlib.TestCase):
    def test_deserialization_fails(self):
        msg = mitogen.core.Message.pickled(EvilObject())
        e = self.assertRaises(mitogen.core.StreamError,
            lambda: msg.unpickle()
        )


class BlobTest(testlib.TestCase):
    klass = mitogen.core.Blob

    # Python 3 pickle protocol 2 does weird stuff depending on whether an empty
    # or nonempty bytes is being serialized. For non-empty, it yields a
    # _codecs.encode() call. For empty, it yields a bytes() call.

    def test_nonempty_bytes(self):
        v = mitogen.core.Blob(b('dave'))
        self.assertEquals(b('dave'), roundtrip(v))

    def test_empty_bytes(self):
        v = mitogen.core.Blob(b(''))
        self.assertEquals(b(''), roundtrip(v))


class ContextTest(testlib.RouterMixin, testlib.TestCase):
    klass = mitogen.core.Context

    # Ensure Context can be round-tripped by regular pickle in addition to
    # Mitogen's hacked pickle. Users may try to call pickle on a Context in
    # strange circumstances, and it's often used to glue pieces of an app
    # together (e.g. Ansible).

    def test_mitogen_roundtrip(self):
        c = self.router.local()
        r = mitogen.core.Receiver(self.router)
        r.to_sender().send(c)
        c2 = r.get().unpickle()
        self.assertEquals(None, c2.router)
        self.assertEquals(c.context_id, c2.context_id)
        self.assertEquals(c.name, c2.name)

    def test_vanilla_roundtrip(self):
        c = self.router.local()
        c2 = pickle.loads(pickle.dumps(c))
        self.assertEquals(None, c2.router)
        self.assertEquals(c.context_id, c2.context_id)
        self.assertEquals(c.name, c2.name)


if __name__ == '__main__':
    unittest2.main()
