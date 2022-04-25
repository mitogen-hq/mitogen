import pickle

import mitogen.core
from mitogen.core import b

import testlib


class PickleTest(testlib.RouterMixin, testlib.TestCase):
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
        self.assertEqual(None, c2.router)
        self.assertEqual(c.context_id, c2.context_id)
        self.assertEqual(c.name, c2.name)

    def test_vanilla_roundtrip(self):
        c = self.router.local()
        c2 = pickle.loads(pickle.dumps(c))
        self.assertEqual(None, c2.router)
        self.assertEqual(c.context_id, c2.context_id)
        self.assertEqual(c.name, c2.name)
