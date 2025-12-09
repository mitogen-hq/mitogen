import fcntl
import functools
import operator

import mitogen.core
import mitogen.parent
from mitogen.core import b

import testlib


def own_create_child(args, blocking, pipe_size=None, preexec_fn=None, pass_stderr=True):
    """
    Create a child process whose stdin/stdout/stderr is connected to a pipe.

    :param list args:
        Program argument vector.
    :param bool blocking:
        If :data:`True`, the pipes use blocking IO, otherwise non-blocking.
    :param int pipe_size:
        If not :data:`None`, use the values as the pipe size.
    :param function preexec_fn:
        If not :data:`None`, a function to run within the post-fork child
        before executing the target program.
    :returns:
        :class:`PopenProcess` instance.
    """
    parent_rfp, child_wfp = mitogen.core.pipe(blocking=blocking)
    child_rfp, parent_wfp = mitogen.core.pipe(blocking=blocking)
    stderr_r, stderr = mitogen.core.pipe(blocking=blocking)
    mitogen.core.set_cloexec(stderr_r.fileno())
    if pipe_size is not None:
        fcntl.fcntl(parent_rfp.fileno(), fcntl.F_SETPIPE_SZ, pipe_size)
        fcntl.fcntl(child_rfp.fileno(), fcntl.F_SETPIPE_SZ, pipe_size)
        fcntl.fcntl(stderr_r.fileno(), fcntl.F_SETPIPE_SZ, pipe_size)
        assert fcntl.fcntl(parent_rfp.fileno(), fcntl.F_GETPIPE_SZ) == pipe_size
        assert fcntl.fcntl(child_rfp.fileno(), fcntl.F_GETPIPE_SZ) == pipe_size
        assert fcntl.fcntl(stderr_r.fileno(), fcntl.F_GETPIPE_SZ) == pipe_size

    try:
        proc = testlib.subprocess.Popen(
            args=args,
            stdin=child_rfp,
            stdout=child_wfp,
            stderr=stderr,
            preexec_fn=preexec_fn,
        )
    except Exception:
        child_rfp.close()
        child_wfp.close()
        parent_rfp.close()
        parent_wfp.close()
        stderr_r.close()
        stderr.close()
        raise

    child_rfp.close()
    child_wfp.close()
    stderr.close()
    # Only used to create a specific test scenario!
    if not pass_stderr:
        stderr_r.close()
        stderr_r = None
    return mitogen.parent.PopenProcess(
        proc=proc,
        stdin=parent_wfp,
        stdout=parent_rfp,
        stderr=stderr_r,
    )


class DummyConnectionBlocking(mitogen.parent.Connection):
    """Dummy blocking IO connection"""

    pipe_size = 4096 if getattr(fcntl, "F_SETPIPE_SZ", None) else None
    create_child = staticmethod(
        functools.partial(own_create_child, blocking=True, pipe_size=pipe_size)
    )
    name_prefix = "dummy_blocking"


class DummyConnectionNonBlocking(mitogen.parent.Connection):
    """Dummy non-blocking IO connection"""

    pipe_size = 4096 if getattr(fcntl, "F_SETPIPE_SZ", None) else None
    create_child = staticmethod(
        functools.partial(own_create_child, blocking=False, pipe_size=pipe_size)
    )
    name_prefix = "dummy_non_blocking"


class ConnectionTest(testlib.RouterMixin, testlib.TestCase):
    def test_non_blocking_stdin(self):
        """Test that first stage works with non-blocking STDIN

        The boot command should read the preamble from STDIN, write all ECO
        markers to STDOUT, and then execute the preamble.

        This test writes the complete preamble to non-blocking STDIN.

        1. Fork child reads from non-blocking STDIN
        2. Fork child writes all data as expected by the protocol.
        3. A context call works as expected.

        """
        log = testlib.LogCapturer()
        log.start()
        ctx = self.router._connect(DummyConnectionNonBlocking, connect_timeout=0.5)
        self.assertEqual(3, ctx.call(operator.add, 1, 2))
        logs = log.stop()

    def test_blocking_stdin(self):
        """Test that first stage works with blocking STDIN

        The boot command should read the preamble from STDIN, write all ECO
        markers to STDOUT, and then execute the preamble.

        This test writes the complete preamble to blocking STDIN.

        1. Fork child reads from blocking STDIN
        2. Fork child writes all data as expected by the protocol.
        3. A context call works as expected.

        """
        log = testlib.LogCapturer()
        log.start()
        ctx = self.router._connect(DummyConnectionBlocking, connect_timeout=0.5)
        self.assertEqual(3, ctx.call(operator.add, 1, 2))
        logs = log.stop()


class CommandLineTest(testlib.RouterMixin, testlib.TestCase):
    # Ensure this version of Python produces a command line that is sufficient
    # to bootstrap this version of Python.
    #
    # TODO:
    #   * 2.7 starting 2.4
    #   * 2.7 starting 3.x
    #   * 3.x starting 2.7

    def setUp(self):
        super(CommandLineTest, self).setUp()
        options = mitogen.parent.Options(max_message_size=123)
        conn = mitogen.parent.Connection(options, self.router)
        conn.context = mitogen.core.Context(None, 123)
        self.args = conn.get_boot_command()
        self.preamble = conn.get_preamble()
        self.conn = conn

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

        fp = open("/dev/zero", "r")
        try:
            proc = testlib.subprocess.Popen(
                self.args,
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

    def test_premature_eof(self):
        """The boot command should write an ECO marker to stdout, read the
        preamble from stdin, then execute it.

        This test writes some data to STDIN and closes it then to create an
        EOF situation.
        1. Fork child tries to read from STDIN, but stops as EOF is received.
        2. Fork child crashes (trying to decompress the junk data)
        3. Fork child's file descriptors (write pipes) are closed by the OS
        4. Fork parent does `dup(<read pipe>, <stdin>)` and `exec(<python>)`
        5. Python reads `b''` (i.e. EOF) from stdin (a closed pipe)
        6. Python runs `''` (a valid script) and exits with success"""

        proc = testlib.subprocess.Popen(
            args=self.args,
            stdout=testlib.subprocess.PIPE,
            stderr=testlib.subprocess.PIPE,
            stdin=testlib.subprocess.PIPE,
        )

        # Do not send all of the data from the preamble
        proc.stdin.write(self.preamble[:-128])
        proc.stdin.flush()
        proc.stdin.close()
        try:
            returncode = proc.wait(timeout=10)
        except testlib.subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=3)
            self.fail("First stage did not handle EOF on STDIN")
        try:
            self.assertEqual(0, returncode)
            self.assertEqual(
                proc.stdout.read(),
                mitogen.parent.BootstrapProtocol.EC0_MARKER + b("\n"),
            )
            self.assertIn(
                b("Error -5 while decompressing data"),
                proc.stderr.read(),
            )
        finally:
            proc.stdout.close()
            proc.stderr.close()

    def test_timeout_error(self):
        """The boot command should write an ECO marker to stdout, try to read
        the preamble from stdin, then fail with an TimeoutError as nothing has
        been written.

        This test writes no data to STDIN of the fork child to enforce a time out.
        1. Fork child tries to read from STDIN, but runs into the timeout
        2. Fork child raises TimeoutError
        3. Fork child's file descriptors (write pipes) are closed by the OS
        4. Fork parent does `dup(<read pipe>, <stdin>)` and `exec(<python>)`
        5. Python reads `b''` (i.e. EOF) from stdin (a closed pipe)
        6. Python runs `''` (a valid script) and exits with success
        """

        # We do not want to wait the default of 10s, change it to 0.1s
        self.conn._first_stage_select_timeout = 0.1
        args = self.conn.get_boot_command()

        proc = testlib.subprocess.Popen(
            args=args,
            stdout=testlib.subprocess.PIPE,
            stderr=testlib.subprocess.PIPE,
            close_fds=True,
        )
        try:
            returncode = proc.wait(timeout=3)
        except testlib.subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=3)
            self.fail("Timeout situation was not recognized")
        else:
            stdout = proc.stdout.read()
            stderr = proc.stderr.read()
        finally:
            proc.stdout.close()
            proc.stderr.close()
        self.assertEqual(0, returncode)
        self.assertEqual(stdout, mitogen.parent.BootstrapProtocol.EC0_MARKER + b("\n"))
        self.assertIn(
            b(""),
            stderr,
        )
