import unittest

import testlib

import stdio_checks


class StdIOMixin(testlib.RouterMixin):
    """
    Test that stdin, stdout, and stderr conform to common expectations,
    such as blocking IO.
    """
    def check_can_write_stdout_1_mib(self, context):
        """
        Writing to stdout should not raise EAGAIN. Regression test for
        https://github.com/mitogen-hq/mitogen/issues/712.
        """
        size = 1 * 2**20
        nwritten = context.call(stdio_checks.shout_stdout, size)
        self.assertEqual(nwritten, size)

    def check_stdio_is_blocking(self, context):
        stdin_blocking, stdout_blocking, stderr_blocking = context.call(
            stdio_checks.stdio_is_blocking,
        )
        self.assertTrue(stdin_blocking)
        self.assertTrue(stdout_blocking)
        self.assertTrue(stderr_blocking)


class LocalTest(StdIOMixin, testlib.TestCase):
    def test_can_write_stdout_1_mib(self):
        self.check_can_write_stdout_1_mib(self.router.local())

    def test_stdio_is_blocking(self):
        self.check_stdio_is_blocking(self.router.local())


class SudoTest(StdIOMixin, testlib.TestCase):
    @unittest.skipIf(not testlib.have_sudo_nopassword(), 'Needs passwordless sudo')
    def test_can_write_stdout_1_mib(self):
        self.check_can_write_stdout_1_mib(self.router.sudo())

    @unittest.skipIf(not testlib.have_sudo_nopassword(), 'Needs passwordless sudo')
    def test_stdio_is_blocking(self):
        self.check_stdio_is_blocking(self.router.sudo())
