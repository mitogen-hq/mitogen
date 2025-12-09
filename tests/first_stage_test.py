import mitogen.core
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
        """Test valid syntax

        The boot command should write an ECO marker to stdout, read the
        preamble from stdin, then execute it.

        This test attaches /dev/zero to stdin to create a specific failure

        1. Fork child reads <compressed preamble size> bytes of NUL (`b'\0'`)
        2. Fork child crashes (trying to decompress the junk data)
        3. Fork child's file descriptors (write pipes) are closed by the OS
        4. Fork parent does `dup(<read pipe>, <stdin>)` and `exec(<python>)`
        5. Python reads `b''` (i.e. EOF) from stdin (a closed pipe)
        6. Python runs `''` (a valid script) and exits with success

        """

        options = mitogen.parent.Options(max_message_size=123)
        conn = mitogen.parent.Connection(options, self.router)
        conn.context = mitogen.core.Context(None, 123)
        fp = open("/dev/zero", "r")
        try:
            proc = testlib.subprocess.Popen(
                args=conn.get_boot_command(),
                stdin=fp,
                stdout=testlib.subprocess.PIPE,
                stderr=testlib.subprocess.PIPE,
            )
            stdout, stderr = proc.communicate()
            self.assertEqual(0, proc.returncode)
            self.assertEqual(stdout,
                mitogen.parent.BootstrapProtocol.EC0_MARKER+b('\n'))
            self.assertIn(
                b("Error -3 while decompressing data"),  # Unknown compression method
                stderr,
            )
        finally:
            fp.close()
