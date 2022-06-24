import fcntl
import os
import stat
import sys
import tempfile

import mitogen.core
import mitogen.parent
from mitogen.core import b

import testlib


def _osx_mode(n):
    """
    fstat(2) on UNIX sockets on OSX return different mode bits depending on
    which side is being inspected, so zero those bits for comparison.
    """
    if sys.platform == 'darwin':
        n &= ~int('0777', 8)
    return n


def run_fd_check(func, fd, mode, on_start=None):
    """
    Run ``tests/data/fd_check.py`` using `func`. The subprocess writes
    information about the `fd` it received to a temporary file.

    :param func:
        Function like `create_child()` used to start child.
    :param fd:
        FD child should read/write from, and report information about.
    :param mode:
        "read" or "write", depending on whether the FD is readable or writeable
        from the perspective of the child. If "read", `on_start()` should write
        "TEST" to it and the child reads "TEST" from it, otherwise `on_start()`
        should read "TEST" from it and the child writes "TEST" to it.
    :param on_start:
        Function invoked as `on_start(proc)`
    :returns:
        Tuple of `(proc, info, on_start_result)`, where:

            * `proc`: the :class:`mitogen.parent.Process` returned by `func`.
            * `info`: dict containing information returned by the child:
                * `buf`: "TEST" that was read in "read" mode
                * `flags`: :attr:`fcntl.F_GETFL` flags for `fd`
                * `st_mode`: st_mode field from :func:`os.fstat`
                * `st_dev`: st_dev field from :func:`os.fstat`
                * `st_ino`: st_ino field from :func:`os.fstat`
                * `ttyname`: :func:`os.ttyname` invoked on `fd`.
                * `controlling_tty`: :func:os.ttyname` invoked on ``/dev/tty``
                  from within the child.
    """
    tf = tempfile.NamedTemporaryFile()
    args = [
        sys.executable,
        testlib.data_path('fd_check.py'),
        tf.name,
        str(fd),
        mode,
    ]

    proc = func(args=args)
    os = None
    if on_start:
        os = on_start(proc)
    proc.proc.wait()
    try:
        return proc, eval(tf.read()), os
    finally:
        tf.close()


def close_proc(proc):
    proc.stdin.close()
    proc.stdout.close()
    if proc.stderr:
        proc.stderr.close()


def wait_read(fp, n):
    poller = mitogen.core.Poller()
    try:
        poller.start_receive(fp.fileno())
        for _ in poller.poll():
            return os.read(fp.fileno(), n)
        assert False
    finally:
        poller.close()


class StdinSockMixin(object):
    def test_stdin(self):
        proc, info, _ = run_fd_check(self.func, 0, 'read',
            lambda proc: proc.stdin.send(b('TEST')))
        st = os.fstat(proc.stdin.fileno())
        self.assertTrue(stat.S_ISSOCK(st.st_mode))
        self.assertEqual(st.st_dev, info['st_dev'])
        self.assertEqual(st.st_mode, _osx_mode(info['st_mode']))
        flags = fcntl.fcntl(proc.stdin.fileno(), fcntl.F_GETFL)
        self.assertTrue(flags & os.O_RDWR)
        self.assertTrue(info['buf'], 'TEST')
        self.assertTrue(info['flags'] & os.O_RDWR)


class StdoutSockMixin(object):
    def test_stdout(self):
        proc, info, buf = run_fd_check(self.func, 1, 'write',
            lambda proc: wait_read(proc.stdout, 4))
        st = os.fstat(proc.stdout.fileno())
        self.assertTrue(stat.S_ISSOCK(st.st_mode))
        self.assertEqual(st.st_dev, info['st_dev'])
        self.assertEqual(st.st_mode, _osx_mode(info['st_mode']))
        flags = fcntl.fcntl(proc.stdout.fileno(), fcntl.F_GETFL)
        self.assertTrue(flags & os.O_RDWR)
        self.assertTrue(buf, 'TEST')
        self.assertTrue(info['flags'] & os.O_RDWR)


class CreateChildTest(StdinSockMixin, StdoutSockMixin, testlib.TestCase):
    func = staticmethod(mitogen.parent.create_child)

    def test_stderr(self):
        proc, info, _ = run_fd_check(self.func, 2, 'write')
        st = os.fstat(sys.stderr.fileno())
        self.assertEqual(st.st_dev, info['st_dev'])
        self.assertEqual(st.st_mode, info['st_mode'])
        self.assertEqual(st.st_ino, info['st_ino'])


class CreateChildMergedTest(StdinSockMixin, StdoutSockMixin,
                            testlib.TestCase):
    def func(self, *args, **kwargs):
        kwargs['merge_stdio'] = True
        return mitogen.parent.create_child(*args, **kwargs)

    def test_stderr(self):
        proc, info, buf = run_fd_check(self.func, 2, 'write',
            lambda proc: wait_read(proc.stdout, 4))
        self.assertEqual(None, proc.stderr)
        st = os.fstat(proc.stdout.fileno())
        self.assertTrue(stat.S_ISSOCK(st.st_mode))
        flags = fcntl.fcntl(proc.stdout.fileno(), fcntl.F_GETFL)
        self.assertTrue(flags & os.O_RDWR)
        self.assertTrue(buf, 'TEST')
        self.assertTrue(info['flags'] & os.O_RDWR)


class CreateChildStderrPipeTest(StdinSockMixin, StdoutSockMixin,
                                testlib.TestCase):
    def func(self, *args, **kwargs):
        kwargs['stderr_pipe'] = True
        return mitogen.parent.create_child(*args, **kwargs)

    def test_stderr(self):
        proc, info, buf = run_fd_check(self.func, 2, 'write',
            lambda proc: wait_read(proc.stderr, 4))
        st = os.fstat(proc.stderr.fileno())
        self.assertTrue(stat.S_ISFIFO(st.st_mode))
        self.assertEqual(st.st_dev, info['st_dev'])
        self.assertEqual(st.st_mode, info['st_mode'])
        flags = fcntl.fcntl(proc.stderr.fileno(), fcntl.F_GETFL)
        self.assertFalse(flags & os.O_WRONLY)
        self.assertFalse(flags & os.O_RDWR)
        self.assertTrue(buf, 'TEST')
        self.assertTrue(info['flags'] & os.O_WRONLY)


class TtyCreateChildTest(testlib.TestCase):
    func = staticmethod(mitogen.parent.tty_create_child)

    def test_dev_tty_open_succeeds(self):
        # In the early days of UNIX, a process that lacked a controlling TTY
        # would acquire one simply by opening an existing TTY. Linux and OS X
        # continue to follow this behaviour, however at least FreeBSD moved to
        # requiring an explicit ioctl(). Linux supports it, but we don't yet
        # use it there and anyway the behaviour will never change, so no point
        # in fixing things that aren't broken. Below we test that
        # getpass-loving apps like sudo and ssh get our slave PTY when they
        # attempt to open /dev/tty, which is what they both do on attempting to
        # read a password.
        tf = tempfile.NamedTemporaryFile()
        try:
            proc = self.func([
                'bash', '-c', 'exec 2>%s; echo hi > /dev/tty' % (tf.name,)
            ])
            mitogen.core.set_block(proc.stdin.fileno())
            # read(3) below due to https://bugs.python.org/issue37696
            self.assertEqual(mitogen.core.b('hi\n'), proc.stdin.read(3))
            waited_pid, status = os.waitpid(proc.pid, 0)
            self.assertEqual(proc.pid, waited_pid)
            self.assertEqual(0, status)
            self.assertEqual(mitogen.core.b(''), tf.read())
            proc.stdout.close()
        finally:
            tf.close()

    def test_stdin(self):
        proc, info, _ = run_fd_check(self.func, 0, 'read',
            lambda proc: proc.stdin.write(b('TEST')))
        st = os.fstat(proc.stdin.fileno())
        self.assertTrue(stat.S_ISCHR(st.st_mode))
        self.assertTrue(stat.S_ISCHR(info['st_mode']))

        self.assertTrue(isinstance(info['ttyname'],
                        mitogen.core.UnicodeType))
        self.assertTrue(os.isatty(proc.stdin.fileno()))

        flags = fcntl.fcntl(proc.stdin.fileno(), fcntl.F_GETFL)
        self.assertTrue(flags & os.O_RDWR)
        self.assertTrue(info['flags'] & os.O_RDWR)
        self.assertTrue(info['buf'], 'TEST')

    def test_stdout(self):
        proc, info, buf = run_fd_check(self.func, 1, 'write',
            lambda proc: wait_read(proc.stdout, 4))

        st = os.fstat(proc.stdout.fileno())
        self.assertTrue(stat.S_ISCHR(st.st_mode))
        self.assertTrue(stat.S_ISCHR(info['st_mode']))

        self.assertTrue(isinstance(info['ttyname'],
                        mitogen.core.UnicodeType))
        self.assertTrue(os.isatty(proc.stdout.fileno()))

        flags = fcntl.fcntl(proc.stdout.fileno(), fcntl.F_GETFL)
        self.assertTrue(flags & os.O_RDWR)
        self.assertTrue(info['flags'] & os.O_RDWR)

        self.assertTrue(flags & os.O_RDWR)
        self.assertTrue(buf, 'TEST')

    def test_stderr(self):
        # proc.stderr is None in the parent since there is no separate stderr
        # stream. In the child, FD 2/stderr is connected to the TTY.
        proc, info, buf = run_fd_check(self.func, 2, 'write',
            lambda proc: wait_read(proc.stdout, 4))

        st = os.fstat(proc.stdout.fileno())
        self.assertTrue(stat.S_ISCHR(st.st_mode))
        self.assertTrue(stat.S_ISCHR(info['st_mode']))

        self.assertTrue(isinstance(info['ttyname'],
                        mitogen.core.UnicodeType))
        self.assertTrue(os.isatty(proc.stdout.fileno()))

        flags = fcntl.fcntl(proc.stdout.fileno(), fcntl.F_GETFL)
        self.assertTrue(flags & os.O_RDWR)
        self.assertTrue(info['flags'] & os.O_RDWR)

        self.assertTrue(flags & os.O_RDWR)
        self.assertTrue(buf, 'TEST')

    def test_dev_tty_open_succeeds(self):
        # In the early days of UNIX, a process that lacked a controlling TTY
        # would acquire one simply by opening an existing TTY. Linux and OS X
        # continue to follow this behaviour, however at least FreeBSD moved to
        # requiring an explicit ioctl(). Linux supports it, but we don't yet
        # use it there and anyway the behaviour will never change, so no point
        # in fixing things that aren't broken. Below we test that
        # getpass-loving apps like sudo and ssh get our slave PTY when they
        # attempt to open /dev/tty, which is what they both do on attempting to
        # read a password.
        tf = tempfile.NamedTemporaryFile()
        try:
            proc = self.func([
                'bash', '-c', 'exec 2>%s; echo hi > /dev/tty' % (tf.name,)
            ])
            self.assertEqual(mitogen.core.b('hi\n'), wait_read(proc.stdout, 3))
            waited_pid, status = os.waitpid(proc.pid, 0)
            self.assertEqual(proc.pid, waited_pid)
            self.assertEqual(0, status)
            self.assertEqual(mitogen.core.b(''), tf.read())
            proc.stdout.close()
        finally:
            tf.close()


class StderrDiagTtyMixin(object):
    def test_stderr(self):
        # proc.stderr is the PTY master, FD 2 in the child is the PTY slave
        proc, info, buf = run_fd_check(self.func, 2, 'write',
            lambda proc: wait_read(proc.stderr, 4))

        st = os.fstat(proc.stderr.fileno())
        self.assertTrue(stat.S_ISCHR(st.st_mode))
        self.assertTrue(stat.S_ISCHR(info['st_mode']))

        self.assertTrue(isinstance(info['ttyname'],
                        mitogen.core.UnicodeType))
        self.assertTrue(os.isatty(proc.stderr.fileno()))

        flags = fcntl.fcntl(proc.stderr.fileno(), fcntl.F_GETFL)
        self.assertTrue(flags & os.O_RDWR)
        self.assertTrue(info['flags'] & os.O_RDWR)

        self.assertTrue(flags & os.O_RDWR)
        self.assertTrue(buf, 'TEST')


class HybridTtyCreateChildTest(StdinSockMixin, StdoutSockMixin,
                               StderrDiagTtyMixin, testlib.TestCase):
    func = staticmethod(mitogen.parent.hybrid_tty_create_child)



if 0:
    # issue #410
    class SelinuxHybridTtyCreateChildTest(StderrDiagTtyMixin, testlib.TestCase):
        func = staticmethod(mitogen.parent.selinux_hybrid_tty_create_child)

        def test_stdin(self):
            proc, info, buf = run_fd_check(self.func, 0, 'read',
                lambda proc: proc.transmit_side.write('TEST'))
            st = os.fstat(proc.transmit_side.fd)
            self.assertTrue(stat.S_ISFIFO(st.st_mode))
            self.assertEqual(st.st_dev, info['st_dev'])
            self.assertEqual(st.st_mode, info['st_mode'])
            flags = fcntl.fcntl(proc.transmit_side.fd, fcntl.F_GETFL)
            self.assertTrue(flags & os.O_WRONLY)
            self.assertTrue(buf, 'TEST')
            self.assertFalse(info['flags'] & os.O_WRONLY)
            self.assertFalse(info['flags'] & os.O_RDWR)

        def test_stdout(self):
            proc, info, buf = run_fd_check(self.func, 1, 'write',
                lambda proc: wait_read(proc.receive_side, 4))
            st = os.fstat(proc.receive_side.fd)
            self.assertTrue(stat.S_ISFIFO(st.st_mode))
            self.assertEqual(st.st_dev, info['st_dev'])
            self.assertEqual(st.st_mode, info['st_mode'])
            flags = fcntl.fcntl(proc.receive_side.fd, fcntl.F_GETFL)
            self.assertFalse(flags & os.O_WRONLY)
            self.assertFalse(flags & os.O_RDWR)
            self.assertTrue(info['flags'] & os.O_WRONLY)
            self.assertTrue(buf, 'TEST')
