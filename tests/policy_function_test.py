try:
    from unittest import mock
except ImportError:
    import mock

import mitogen.core
import mitogen.parent

import testlib


class HasParentAuthorityTest(testlib.TestCase):
    func = staticmethod(mitogen.core.has_parent_authority)

    def call(self, auth_id):
        msg = mitogen.core.Message(auth_id=auth_id)
        return self.func(msg)

    @mock.patch('mitogen.context_id', 5555)
    @mock.patch('mitogen.parent_ids', [111, 222])
    def test_okay(self):
        self.assertFalse(self.call(0))
        self.assertTrue(self.call(5555))
        self.assertTrue(self.call(111))


class IsImmediateChildTest(testlib.TestCase):
    func = staticmethod(mitogen.core.has_parent_authority)

    def call(self, auth_id, remote_id):
        msg = mitogen.core.Message(auth_id=auth_id)
        stream = mock.Mock(remote_id=remote_id)
        return self.func(msg, stream)

    def test_okay(self):
        self.assertFalse(0, 1)
        self.assertTrue(1, 1)
