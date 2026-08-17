import pickle

import mitogen.core
import mitogen.parent

import testlib


class CoreMixin(object):
    context_class = mitogen.core.Context


class ParentMixin(object):
    context_class = mitogen.parent.Context


class TestsMixin(object):
    def test_required_attrs(self):
        router = object()
        ctx = self.context_class(router, 42)
        self.assertEqual(ctx.router, router)
        self.assertEqual(ctx.context_id, 42)

    def test_name_attr(self):
        for arg, expected_val, expected_type in [
            (mitogen.core.b(''),        u'',        mitogen.core.UnicodeType),
            (mitogen.core.b('fred'),    u'fred',    mitogen.core.UnicodeType),
            (u'',                       u'',        mitogen.core.UnicodeType),
            (u'fred',                   u'fred',    mitogen.core.UnicodeType),
        ]:
            ctx = self.context_class(None, 42, arg)
            self.assertEqual(ctx.name, expected_val)
            self.assertTrue(isinstance(ctx.name, expected_type))

    def test_name_type(self):
        self.assertRaises(TypeError, self.context_class, None, 42, 43)

    def test_name_length(self):
        too_long = u'a' * (self.context_class.NAME_MAX_LEN + 1)
        self.assertRaises(ValueError, self.context_class, None, 42, too_long)


class CoreTest(TestsMixin, ParentMixin, testlib.TestCase):
    pass


class ParentTest(TestsMixin, ParentMixin, testlib.TestCase):
    pass


class PickleTest(testlib.RouterMixin, testlib.TestCase):
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
