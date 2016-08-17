
import mock
import subprocess
import unittest
import sys

import econtext.master
import econtext.master
import testlib

import plain_old_module
import simple_pkg.a


class GoodModulesTest(testlib.BrokerMixin, unittest.TestCase):
    def test_plain_old_module(self):
        # The simplest case: a top-level module with no interesting imports or
        # package machinery damage.
        context = self.broker.get_local()
        self.assertEquals(256, context.call(plain_old_module.pow, 2, 8))

    def test_simple_pkg(self):
        # Ensure success of a simple package containing two submodules, one of
        # which imports the other.
        context = self.broker.get_local()
        self.assertEquals(3,
            context.call(simple_pkg.a.subtract_one_add_two, 2))

    def test_self_contained_program(self):
        # Ensure a program composed of a single script can be imported
        # successfully.
        args = [sys.executable, testlib.data_path('self_contained_program.py')]
        output = subprocess.check_output(args)
        self.assertEquals(output, "['__main__', 50]\n")


class BrokenModulesTest(unittest.TestCase):
    def test_obviously_missing(self):
        # Ensure we don't crash in the case of a module legitimately being
        # unavailable. Should never happen in the real world.

        context = mock.Mock()
        responder = econtext.master.ModuleResponder(context)
        responder.get_module((50, 'non_existent_module'))
        self.assertEquals(1, len(context.enqueue.mock_calls))

        call = context.enqueue.mock_calls[0]
        reply_to, data = call[1]
        self.assertEquals(50, reply_to)
        self.assertTrue(data is None)

    def test_ansible_six_messed_up_path(self):
        # The copy of six.py shipped with Ansible appears in a package whose
        # __path__ subsequently ends up empty, which prevents pkgutil from
        # finding its submodules. After ansible.compat.six is initialized in
        # the parent, attempts to execute six/__init__.py on the slave will
        # cause an attempt to request ansible.compat.six._six from the master.
        import six_brokenpkg

        context = mock.Mock()
        responder = econtext.master.ModuleResponder(context)
        responder.get_module((50, 'six_brokenpkg._six'))
        self.assertEquals(1, len(context.enqueue.mock_calls))

        call = context.enqueue.mock_calls[0]
        reply_to, data = call[1]
        self.assertEquals(50, reply_to)
        self.assertTrue(isinstance(data, tuple))
