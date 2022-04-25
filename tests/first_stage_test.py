import subprocess

import mitogen.parent
from mitogen.core import b

import testlib


class CommandLineTest(testlib.RouterMixin, testlib.TestCase):
    # Ensure this version of Python produces a command line that is sufficient
    # to bootstrap this version of Python.
    #
    # TODO:
    #   * 2.7 starting 2.4
    #   * 2.7 starting 3.x
    #   * 3.x starting 2.7

    def test_valid_syntax(self):
        options = mitogen.parent.Options(max_message_size=123)
        conn = mitogen.parent.Connection(options, self.router)
        conn.context = mitogen.core.Context(None, 123)
        args = conn.get_boot_command()

        # Executing the boot command will print "EC0" and expect to read from
        # stdin, which will fail because it's pointing at /dev/null, causing
        # the forked child to crash with an EOFError and disconnect its write
        # pipe. The forked and freshly execed parent will get a 0-byte read
        # from the pipe, which is a valid script, and therefore exit indicating
        # success.

        fp = open("/dev/null", "r")
        try:
            proc = subprocess.Popen(args,
                stdin=fp,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            stdout, stderr = proc.communicate()
            self.assertEqual(0, proc.returncode)
            self.assertEqual(stdout,
                mitogen.parent.BootstrapProtocol.EC0_MARKER+b('\n'))
            self.assertIn(b("Error -5 while decompressing data"), stderr)
        finally:
            fp.close()
