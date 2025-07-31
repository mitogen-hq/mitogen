import testlib

import stdio_checks


class StdIOTest(testlib.RouterMixin, testlib.TestCase):
    """
    Test that stdin, stdout, and stderr conform to common expectations,
    such as blocking IO.
    """
    def test_can_write_stdout_1_mib(self):
        """
        Writing to stdout should not raise EAGAIN. Regression test for
        https://github.com/mitogen-hq/mitogen/issues/712.
        """
        size = 1 * 2**20
        context = self.router.local()
        result = context.call(stdio_checks.shout_stdout, size)
        self.assertEqual('success', result)

    def test_stdio_is_blocking(self):
        context = self.router.local()
        stdin_blocking, stdout_blocking, stderr_blocking = context.call(
            stdio_checks.stdio_is_blocking,
        )
        self.assertTrue(stdin_blocking)
        self.assertTrue(stdout_blocking)
        self.assertTrue(stderr_blocking)
