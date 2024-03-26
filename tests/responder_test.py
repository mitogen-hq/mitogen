import textwrap
import subprocess
import sys
import unittest

try:
    from unittest import mock
except ImportError:
    import mock

import mitogen.master
import testlib

import plain_old_module
import simple_pkg.a


class NeutralizeMainTest(testlib.RouterMixin, testlib.TestCase):
    klass = mitogen.master.ModuleResponder

    def call(self, *args, **kwargs):
        router = mock.Mock()
        return self.klass(router).neutralize_main(*args, **kwargs)

    def test_missing_exec_guard(self):
        path = testlib.data_path('main_with_no_exec_guard.py')
        args = [sys.executable, path]
        proc = subprocess.Popen(args, stderr=subprocess.PIPE)
        _, stderr = proc.communicate()
        self.assertEqual(1, proc.returncode)
        expect = self.klass.main_guard_msg % (path,)
        self.assertIn(expect, stderr.decode())

    HAS_MITOGEN_MAIN = mitogen.core.b(
        textwrap.dedent("""
            herp derp

            def myprog():
                pass

            @mitogen.main(maybe_some_option=True)
            def main(router):
                pass
        """)
    )

    def test_mitogen_main(self):
        untouched = self.call("derp.py", self.HAS_MITOGEN_MAIN)
        self.assertEqual(untouched, self.HAS_MITOGEN_MAIN)

    HAS_EXEC_GUARD = mitogen.core.b(
        textwrap.dedent("""
            herp derp

            def myprog():
                pass

            def main():
                pass

            if __name__ == '__main__':
                main()
        """)
    )

    def test_exec_guard(self):
        touched = self.call("derp.py", self.HAS_EXEC_GUARD)
        bits = touched.decode().split()
        self.assertEqual(bits[-3:], ['def', 'main():', 'pass'])


class GoodModulesTest(testlib.RouterMixin, testlib.TestCase):
    def test_plain_old_module(self):
        # The simplest case: a top-level module with no interesting imports or
        # package machinery damage.
        context = self.router.local()

        self.assertEqual(256, context.call(plain_old_module.pow, 2, 8))
        os_fork = int(sys.version_info < (2, 6))  # mitogen.os_fork
        self.assertEqual(1+os_fork, self.router.responder.get_module_count)
        self.assertEqual(1+os_fork, self.router.responder.good_load_module_count)
        self.assertLess(300, self.router.responder.good_load_module_size)

    def test_simple_pkg(self):
        # Ensure success of a simple package containing two submodules, one of
        # which imports the other.
        context = self.router.local()
        self.assertEqual(3,
            context.call(simple_pkg.a.subtract_one_add_two, 2))
        os_fork = int(sys.version_info < (2, 6))  # mitogen.os_fork
        self.assertEqual(2+os_fork, self.router.responder.get_module_count)
        self.assertEqual(3+os_fork, self.router.responder.good_load_module_count)
        self.assertEqual(0, self.router.responder.bad_load_module_count)
        self.assertLess(450, self.router.responder.good_load_module_size)

    def test_self_contained_program(self):
        # Ensure a program composed of a single script can be imported
        # successfully.
        args = [sys.executable, testlib.data_path('self_contained_program.py')]
        proc = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        b_stdout, _ = proc.communicate()
        self.assertEqual(proc.returncode, 0)
        self.assertEqual(b_stdout.decode(), "['__main__', 50]\n")


class BrokenModulesTest(testlib.TestCase):
    def test_obviously_missing(self):
        # Ensure we don't crash in the case of a module legitimately being
        # unavailable. Should never happen in the real world.

        stream = mock.Mock()
        stream.protocol.sent_modules = set()
        router = mock.Mock()
        router.stream_by_id = lambda n: stream

        msg = mitogen.core.Message(
            data=mitogen.core.b('non_existent_module'),
            reply_to=50,
        )
        msg.router = router

        responder = mitogen.master.ModuleResponder(router)
        responder._on_get_module(msg)
        self.assertEqual(1, len(router._async_route.mock_calls))

        self.assertEqual(1, responder.get_module_count)
        self.assertEqual(0, responder.good_load_module_count)
        self.assertEqual(0, responder.good_load_module_size)
        self.assertEqual(1, responder.bad_load_module_count)

        call = router._async_route.mock_calls[0]
        msg, = call[1]
        self.assertEqual(mitogen.core.LOAD_MODULE, msg.handle)
        self.assertEqual(('non_existent_module', None, None, None, ()),
                          msg.unpickle())

    @unittest.skipIf(
        condition=sys.version_info < (2, 6),
        reason='Ancient Python lacked "from . import foo"',
    )
    def test_ansible_six_messed_up_path(self):
        # The copy of six.py shipped with Ansible appears in a package whose
        # __path__ subsequently ends up empty, which prevents pkgutil from
        # finding its submodules. After ansible.compat.six is initialized in
        # the parent, attempts to execute six/__init__.py on the slave will
        # cause an attempt to request ansible.compat.six._six from the master.
        import six_brokenpkg

        stream = mock.Mock()
        stream.protocol.sent_modules = set()
        router = mock.Mock()
        router.stream_by_id = lambda n: stream

        msg = mitogen.core.Message(
            data=mitogen.core.b('six_brokenpkg._six'),
            reply_to=50,
        )
        msg.router = router

        responder = mitogen.master.ModuleResponder(router)
        responder._on_get_module(msg)
        self.assertEqual(1, len(router._async_route.mock_calls))

        self.assertEqual(1, responder.get_module_count)
        self.assertEqual(1, responder.good_load_module_count)
        self.assertEqual(0, responder.bad_load_module_count)

        call = router._async_route.mock_calls[0]
        msg, = call[1]
        self.assertEqual(mitogen.core.LOAD_MODULE, msg.handle)

        tup = msg.unpickle()
        self.assertIsInstance(tup, tuple)


class ForwardTest(testlib.RouterMixin, testlib.TestCase):
    def test_forward_to_nonexistent_context(self):
        nonexistent = mitogen.core.Context(self.router, 123)
        capture = testlib.LogCapturer()
        capture.start()
        self.broker.defer_sync(lambda:
            self.router.responder.forward_modules(
                nonexistent,
                ['mitogen.core']
            )
        )
        s = capture.stop()
        self.assertIn('dropping forward of', s)

    def test_stats(self):
        # Forwarding stats broken because forwarding is broken. See #469.
        c1 = self.router.local()
        c2 = self.router.local(via=c1)

        os_fork = int(sys.version_info < (2, 6))
        self.assertEqual(256, c2.call(plain_old_module.pow, 2, 8))
        self.assertEqual(2+os_fork, self.router.responder.get_module_count)
        self.assertEqual(2+os_fork, self.router.responder.good_load_module_count)
        self.assertLess(10000, self.router.responder.good_load_module_size)
        self.assertGreater(40000, self.router.responder.good_load_module_size)


class BlacklistTest(testlib.TestCase):
    @unittest.skip('implement me')
    def test_whitelist_no_blacklist(self):
        assert 0

    @unittest.skip('implement me')
    def test_whitelist_has_blacklist(self):
        assert 0

    @unittest.skip('implement me')
    def test_blacklist_no_whitelist(self):
        assert 0

    @unittest.skip('implement me')
    def test_blacklist_has_whitelist(self):
        assert 0
