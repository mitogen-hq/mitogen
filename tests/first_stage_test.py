import errno
import operator
import os

import mitogen.core
import mitogen.parent
from mitogen.core import b

import testlib


def create_child_using_pipes(args, blocking, preexec_fn=None):
    """
    Create a child process whose stdin/stdout/stderr is connected to a pipe.

    :param list args:
        Program argument vector.
    :param bool blocking:
        If :data:`True`, the sockets use blocking IO, otherwise non-blocking.
    :param function preexec_fn:
        If not :data:`None`, a function to run within the post-fork child
        before executing the target program.
    :returns:
        :class:`PopenProcess` instance.
    """

    parent_rfp, child_wfp = mitogen.core.pipe(blocking)
    child_rfp, parent_wfp = mitogen.core.pipe(blocking)
    stderr_r, stderr = mitogen.core.pipe(blocking=blocking)
    mitogen.core.set_cloexec(stderr_r.fileno())
    try:
        proc = testlib.subprocess.Popen(
            args=args,
            stdin=child_rfp,
            stdout=child_wfp,
            stderr=stderr,
            close_fds=True,
            preexec_fn=preexec_fn,
        )
    except Exception:
        parent_rfp.close()
        parent_wfp.close()
        stderr_r.close()
        raise
    finally:
        child_rfp.close()
        child_wfp.close()
        stderr.close()

    return mitogen.parent.PopenProcess(
        proc=proc,
        stdin=parent_wfp,
        stdout=parent_rfp,
        stderr=stderr_r,
    )


def create_child_using_sockets(args, blocking, size=None, preexec_fn=None):
    """
    Create a child process whose stdin/stdout is connected to a socket and stderr to a pipe.

    :param list args:
        Program argument vector.
    :param bool blocking:
        If :data:`True`, the sockets use blocking IO, otherwise non-blocking.
    :param int size:
        If not :data:`None`, use the value as the socket buffer size.
    :param function preexec_fn:
        If not :data:`None`, a function to run within the post-fork child
        before executing the target program.
    :returns:
        :class:`PopenProcess` instance.
    """

    parent_rw_fp, child_rw_fp = mitogen.parent.create_socketpair(size=size, blocking=blocking)
    stderr_r, stderr = mitogen.core.pipe(blocking=blocking)
    mitogen.core.set_cloexec(stderr_r.fileno())
    try:
        proc = testlib.subprocess.Popen(
            args=args,
            stdin=child_rw_fp,
            stdout=child_rw_fp,
            stderr=stderr,
            close_fds=True,
            preexec_fn=preexec_fn,
        )
    except Exception:
        parent_rw_fp.close()
        stderr_r.close()
        raise
    finally:
        child_rw_fp.close()
        stderr.close()

    return mitogen.parent.PopenProcess(
        proc=proc,
        stdin=parent_rw_fp,
        stdout=parent_rw_fp,
        stderr=stderr_r,
    )


class DummyConnectionBlocking(mitogen.parent.Connection):
    """Dummy blocking IO connection"""

    create_child = staticmethod(create_child_using_sockets)
    name_prefix = "dummy_blocking"

    #: Dictionary of extra kwargs passed to :attr:`create_child`.
    #: Use a size smaller than the conn.get_preamble() size so multiple
    #: read-calls are needed in the first stage.
    create_child_args = {"blocking": True, "size": 4096}


class DummyConnectionNonBlocking(mitogen.parent.Connection):
    """Dummy non-blocking IO connection"""

    create_child = staticmethod(create_child_using_sockets)
    name_prefix = "dummy_non_blocking"

    #: Dictionary of extra kwargs passed to :attr:`create_child`.
    #: Use a size smaller than the conn.get_preamble() size so multiple
    #: read-calls are needed in the first stage.
    create_child_args = {"blocking": False, "size": 4096}


class DummyConnectionEOFRead(mitogen.parent.Connection):
    """Dummy connection that triggers an EOF-read(STDIN) in the first_stage"""

    name_prefix = "dummy_eof_read"

    #: Dictionary of extra kwargs passed to :attr:`create_child`.
    create_child_args = {"blocking": True}

    @staticmethod
    def create_child(*a, **kw):
        proc = create_child_using_pipes(*a, **kw)
        # Close the pipe -> results in an EOF-read(STDIN) in the first_stage
        proc.stdin.close()
        # Whatever the parent writes to the child, drop it.
        proc.stdin = open("/dev/null", "wb")
        return proc


class DummyConnectionEndlessBlockingRead(mitogen.parent.Connection):
    """Dummy connection that triggers a non-returning read(STDIN) call in the
    first_stage.

    """

    name_prefix = "dummy_endless_blocking_read"

    #: Dictionary of extra kwargs passed to :attr:`create_child`.
    create_child_args = {"blocking": True}

    @staticmethod
    def create_child(*a, **kw):
        proc = create_child_using_pipes(*a, **kw)
        # Keep the pipe open by having a reference to it, otherwise it would be
        # automatically closed by the garbage collector.
        proc._mitogen_test_orig_stdin = proc.stdin
        # Whatever the parent writes to the child, drop it -> read from STDOUT
        # blocks forever in the fork child as no data could be read.
        proc.stdin = open("/dev/null", "wb")
        return proc


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
        with testlib.LogCapturer() as _:
            ctx = self.router._connect(DummyConnectionNonBlocking, connect_timeout=0.5)
            self.assertEqual(3, ctx.call(operator.add, 1, 2))

    def test_blocking_stdin(self):
        """Test that first stage works with blocking STDIN

        The boot command should read the preamble from STDIN, write all ECO
        markers to STDOUT, and then execute the preamble.

        This test writes the complete preamble to blocking STDIN.

        1. Fork child reads from blocking STDIN
        2. Fork child writes all data as expected by the protocol.
        3. A context call works as expected.

        """
        with testlib.LogCapturer() as _:
            ctx = self.router._connect(DummyConnectionBlocking, connect_timeout=0.5)
            self.assertEqual(3, ctx.call(operator.add, 1, 2))

    def test_broker_connect_eof_error(self):
        """Test that broker takes care about EOF errors in the first stage

        The boot command should write an ECO marker to stdout, try to read the
        preamble from STDIN. This read returns with an EOF and the process exits.

        This test writes closes the pipe for STDIN of the fork child to enforce an EOF read call.
        1. Fork child reads from STDIN and reads an EOF and breaks the read-loop
        2. Decompressing the received data results in an error
        3. The child process exits
        4. The streams get disconnected -> mitogen.parent.EofError is raised

        """

        with testlib.LogCapturer() as _:
            e = self.assertRaises(mitogen.parent.EofError,
                              self.router._connect, DummyConnectionEOFRead, connect_timeout=0.5)
            self.assertIn("Error -5 while decompressing data", str(e))

            # Test that a TimeoutError is raised by the broker and all resources
            # are cleaned up.
            options = mitogen.parent.Options(
                old_router=self.router,
                max_message_size=self.router.max_message_size,
                connect_timeout=0.5,
            )
            conn = DummyConnectionEOFRead(options, router=self.router)
            e = self.assertRaises(mitogen.parent.EofError,
                                  conn.connect, context=mitogen.core.Context(None, 1234))
            self.assertIn("Error -5 while decompressing data", str(e))
            # Ensure the child process is reaped if the connection times out.
            testlib.wait_for_child(conn.proc.pid)
            e = self.assertRaises(OSError,
                                  os.kill, conn.proc.pid, 0)
            self.assertEqual(e.args[0], errno.ESRCH)

    def test_broker_connect_timeout_because_endless_blocking_read(self):
        """Test that broker takes care about connection timeouts

        The boot command should write an ECO marker to stdout, try to read the
        preamble from STDIN. This read blocks forever as the parent does write
        all the data to /dev/null instead of the pipe. The broker should then
        raise a TimeoutError as the child needs too much time.

        This test writes no data to STDIN of the fork child to enforce a blocking read call.
        1. Fork child tries to read from STDIN, but blocks forever.
        2. Parent connection timeout timer pops up and the parent cleans up
           everything from the child (e.g. kills the child process).
        3. TimeoutError is raised in the connect call

        """
        with testlib.LogCapturer() as _:
            # Ensure the child process is reaped if the connection times out.
            options = mitogen.parent.Options(
                old_router=self.router,
                max_message_size=self.router.max_message_size,
                connect_timeout=0.5,
            )

            conn = DummyConnectionEndlessBlockingRead(options, router=self.router)
            try:
                self.assertRaises(mitogen.core.TimeoutError,
                                  lambda: conn.connect(context=mitogen.core.Context(None, 1234))
                                  )
                testlib.wait_for_child(conn.proc.pid)
                e = self.assertRaises(OSError,
                                      os.kill, conn.proc.pid, 0)
                self.assertEqual(e.args[0], errno.ESRCH)
            finally:
                conn.proc._mitogen_test_orig_stdin.close()


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
        fp = open("/dev/zero", "rb")
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
                mitogen.core.EC0 + b('\n'))
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

        options = mitogen.parent.Options(max_message_size=123)
        conn = mitogen.parent.Connection(options, self.router)
        conn.context = mitogen.core.Context(None, 123)
        proc = testlib.subprocess.Popen(
            args=conn.get_boot_command(),
            stdout=testlib.subprocess.PIPE,
            stderr=testlib.subprocess.PIPE,
            stdin=testlib.subprocess.PIPE,
        )

        # Do not send all of the data from the preamble
        proc.stdin.write(conn.get_preamble()[:-128])
        proc.stdin.close()
        try:
            returncode = proc.wait(timeout=1)
        except testlib.subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=3)
            self.fail("First stage did not handle EOF on STDIN")
        try:
            self.assertEqual(0, returncode)
            self.assertEqual(
                proc.stdout.read(),
                mitogen.core.EC0 + b("\n"),
            )
            self.assertIn(
                b("Error -5 while decompressing data"),
                proc.stderr.read(),
            )
        finally:
            proc.stdout.close()
            proc.stderr.close()
