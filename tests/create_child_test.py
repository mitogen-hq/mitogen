
import fcntl
import os
import stat
import sys
import time
import tempfile

import mock
import unittest2

import mitogen.parent

import testlib


def run_fd_check(func, fd, mode, on_start=None):
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
    proc.receive_side.close()
    proc.transmit_side.close()
    if proc.diag_receive_side:
        proc.diag_receive_side.close()
    if proc.diag_transmit_side:
        proc.diag_transmit_side.close()


def wait_read(side, n):
    poller = mitogen.core.Poller()
    try:
        poller.start_receive(side.fd)
        for _ in poller.poll():
            return side.read(n)
        assert False
    finally:
        poller.close()


class StdinSockMixin(object):
    def test_stdin(self):
        proc, info, _ = run_fd_check(self.func, 0, 'read',
            lambda proc: proc.transmit_side.write('TEST'))
        st = os.fstat(proc.transmit_side.fd)
        self.assertTrue(stat.S_ISSOCK(st.st_mode))
        self.assertEquals(st.st_dev, info['st_dev'])
        self.assertEquals(st.st_mode, info['st_mode'])
        flags = fcntl.fcntl(proc.transmit_side.fd, fcntl.F_GETFL)
        self.assertTrue(flags & os.O_RDWR)
        self.assertTrue(info['buf'], 'TEST')
        self.assertTrue(info['flags'] & os.O_RDWR)


class StdoutSockMixin(object):
    def test_stdout(self):
        proc, info, buf = run_fd_check(self.func, 1, 'write',
            lambda proc: wait_read(proc.receive_side, 4))
        st = os.fstat(proc.transmit_side.fd)
        self.assertTrue(stat.S_ISSOCK(st.st_mode))
        self.assertEquals(st.st_dev, info['st_dev'])
        self.assertEquals(st.st_mode, info['st_mode'])
        flags = fcntl.fcntl(proc.receive_side.fd, fcntl.F_GETFL)
        self.assertTrue(flags & os.O_RDWR)
        self.assertTrue(buf, 'TEST')
        self.assertTrue(info['flags'] & os.O_RDWR)


class CreateChildTest(StdinSockMixin, StdoutSockMixin, testlib.TestCase):
    func = staticmethod(mitogen.parent.create_child)

    def test_stderr(self):
        proc, info, _ = run_fd_check(self.func, 2, 'write')
        st = os.fstat(sys.stderr.fileno())
        self.assertEquals(st.st_dev, info['st_dev'])
        self.assertEquals(st.st_mode, info['st_mode'])
        self.assertEquals(st.st_ino, info['st_ino'])


class MergedCreateChildTest(StdinSockMixin, StdoutSockMixin,
                            testlib.TestCase):
    func = staticmethod(mitogen.parent.merged_create_child)

    def test_stderr(self):
        proc, info, buf = run_fd_check(self.func, 2, 'write',
            lambda proc: wait_read(proc.receive_side, 4))
        st = os.fstat(proc.transmit_side.fd)
        self.assertTrue(stat.S_ISSOCK(st.st_mode))
        self.assertEquals(st.st_dev, info['st_dev'])
        self.assertEquals(st.st_mode, info['st_mode'])
        flags = fcntl.fcntl(proc.receive_side.fd, fcntl.F_GETFL)
        self.assertTrue(flags & os.O_RDWR)
        self.assertTrue(buf, 'TEST')
        self.assertTrue(info['flags'] & os.O_RDWR)


class StderrCreateChildTest(StdinSockMixin, StdoutSockMixin,
                            testlib.TestCase):
    func = staticmethod(mitogen.parent.stderr_create_child)

    def test_stderr(self):
        proc, info, buf = run_fd_check(self.func, 2, 'write',
            lambda proc: wait_read(proc.diag_receive_side, 4))
        st = os.fstat(proc.diag_receive_side.fd)
        self.assertTrue(stat.S_ISFIFO(st.st_mode))
        self.assertEquals(st.st_dev, info['st_dev'])
        self.assertEquals(st.st_mode, info['st_mode'])
        flags = fcntl.fcntl(proc.diag_receive_side.fd, fcntl.F_GETFL)
        self.assertFalse(flags & os.O_WRONLY)
        self.assertFalse(flags & os.O_RDWR)
        self.assertTrue(buf, 'TEST')
        self.assertTrue(info['flags'] & os.O_WRONLY)


class TtyCreateChildTest(testlib.TestCase):
    func = staticmethod(mitogen.parent.tty_create_child)

    def test_stdin(self):
        proc, info, _ = run_fd_check(self.func, 0, 'read',
            lambda proc: proc.transmit_side.write('TEST'))
        st = os.fstat(proc.transmit_side.fd)
        self.assertTrue(stat.S_ISCHR(st.st_mode))
        self.assertTrue(stat.S_ISCHR(info['st_mode']))

        self.assertTrue(isinstance(info['ttyname'],
                        mitogen.core.UnicodeType))
        os.ttyname(proc.transmit_side.fd) # crashes if wrong

        flags = fcntl.fcntl(proc.transmit_side.fd, fcntl.F_GETFL)
        self.assertTrue(flags & os.O_RDWR)
        self.assertTrue(info['flags'] & os.O_RDWR)

        self.assertNotEquals(st.st_dev, info['st_dev'])
        self.assertTrue(info['buf'], 'TEST')

    def test_stdout(self):
        proc, info, buf = run_fd_check(self.func, 1, 'write',
            lambda proc: wait_read(proc.receive_side, 4))

        st = os.fstat(proc.receive_side.fd)
        self.assertTrue(stat.S_ISCHR(st.st_mode))
        self.assertTrue(stat.S_ISCHR(info['st_mode']))

        self.assertTrue(isinstance(info['ttyname'],
                        mitogen.core.UnicodeType))
        os.ttyname(proc.transmit_side.fd) # crashes if wrong

        flags = fcntl.fcntl(proc.receive_side.fd, fcntl.F_GETFL)
        self.assertTrue(flags & os.O_RDWR)
        self.assertTrue(info['flags'] & os.O_RDWR)

        self.assertNotEquals(st.st_dev, info['st_dev'])
        self.assertTrue(flags & os.O_RDWR)
        self.assertTrue(buf, 'TEST')

    def test_stderr(self):
        proc, info, buf = run_fd_check(self.func, 2, 'write',
            lambda proc: wait_read(proc.receive_side, 4))

        st = os.fstat(proc.receive_side.fd)
        self.assertTrue(stat.S_ISCHR(st.st_mode))
        self.assertTrue(stat.S_ISCHR(info['st_mode']))

        self.assertTrue(isinstance(info['ttyname'],
                        mitogen.core.UnicodeType))
        os.ttyname(proc.transmit_side.fd) # crashes if wrong

        flags = fcntl.fcntl(proc.receive_side.fd, fcntl.F_GETFL)
        self.assertTrue(flags & os.O_RDWR)
        self.assertTrue(info['flags'] & os.O_RDWR)

        self.assertNotEquals(st.st_dev, info['st_dev'])
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
            deadline = time.time() + 5.0
            mitogen.core.set_block(proc.receive_side.fd)
            self.assertEquals(mitogen.core.b('hi\n'), proc.receive_side.read())
            waited_pid, status = os.waitpid(proc.pid, 0)
            self.assertEquals(proc.pid, waited_pid)
            self.assertEquals(0, status)
            self.assertEquals(mitogen.core.b(''), tf.read())
            proc.receive_side.close()
        finally:
            tf.close()


class StderrDiagTtyMixin(object):
    def test_stderr(self):
        proc, info, buf = run_fd_check(self.func, 2, 'write',
            lambda proc: wait_read(proc.diag_receive_side, 4))

        st = os.fstat(proc.diag_receive_side.fd)
        self.assertTrue(stat.S_ISCHR(st.st_mode))
        self.assertTrue(stat.S_ISCHR(info['st_mode']))

        self.assertTrue(isinstance(info['ttyname'],
                        mitogen.core.UnicodeType))
        os.ttyname(proc.diag_transmit_side.fd) # crashes if wrong

        flags = fcntl.fcntl(proc.diag_receive_side.fd, fcntl.F_GETFL)
        self.assertTrue(flags & os.O_RDWR)
        self.assertTrue(info['flags'] & os.O_RDWR)

        self.assertNotEquals(st.st_dev, info['st_dev'])
        self.assertTrue(flags & os.O_RDWR)
        self.assertTrue(buf, 'TEST')


class HybridTtyCreateChildTest(StdinSockMixin, StdoutSockMixin,
                               StderrDiagTtyMixin, testlib.TestCase):
    func = staticmethod(mitogen.parent.hybrid_tty_create_child)


class SelinuxHybridTtyCreateChildTest(StderrDiagTtyMixin, testlib.TestCase):
    func = staticmethod(mitogen.parent.selinux_hybrid_tty_create_child)

    def test_stdin(self):
        proc, info, buf = run_fd_check(self.func, 0, 'read',
            lambda proc: proc.transmit_side.write('TEST'))
        st = os.fstat(proc.transmit_side.fd)
        self.assertTrue(stat.S_ISFIFO(st.st_mode))
        self.assertEquals(st.st_dev, info['st_dev'])
        self.assertEquals(st.st_mode, info['st_mode'])
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
        self.assertEquals(st.st_dev, info['st_dev'])
        self.assertEquals(st.st_mode, info['st_mode'])
        flags = fcntl.fcntl(proc.receive_side.fd, fcntl.F_GETFL)
        self.assertFalse(flags & os.O_WRONLY)
        self.assertFalse(flags & os.O_RDWR)
        self.assertTrue(info['flags'] & os.O_WRONLY)
        self.assertTrue(buf, 'TEST')


if __name__ == '__main__':
    unittest2.main()
