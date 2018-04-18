import os
import subprocess
import tempfile
import time

import unittest2
import testlib

import mitogen.parent


class StreamErrorTest(testlib.RouterMixin, testlib.TestCase):
    def test_direct_eof(self):
        e = self.assertRaises(mitogen.core.StreamError,
            lambda: self.router.local(
                python_path='true',
                connect_timeout=3,
            )
        )
        self.assertEquals(e.args[0], "EOF on stream; last 300 bytes received: ''")

    def test_via_eof(self):
        # Verify FD leakage does not keep failed process open.
        local = self.router.fork()
        e = self.assertRaises(mitogen.core.StreamError,
            lambda: self.router.local(
                via=local,
                python_path='true',
                connect_timeout=3,
            )
        )
        self.assertEquals(e.args[0], "EOF on stream; last 300 bytes received: ''")

    def test_direct_enoent(self):
        e = self.assertRaises(mitogen.core.StreamError,
            lambda: self.router.local(
                python_path='derp',
                connect_timeout=3,
            )
        )
        prefix = 'Child start failed: [Errno 2] No such file or directory.'
        self.assertTrue(e.args[0].startswith(prefix))

    def test_via_enoent(self):
        local = self.router.fork()
        e = self.assertRaises(mitogen.core.StreamError,
            lambda: self.router.local(
                via=local,
                python_path='derp',
                connect_timeout=3,
            )
        )
        prefix = 'Child start failed: [Errno 2] No such file or directory.'
        self.assertTrue(e.args[0].startswith(prefix))


class ContextTest(testlib.RouterMixin, unittest2.TestCase):
    def test_context_shutdown(self):
        local = self.router.local()
        pid = local.call(os.getpid)
        local.shutdown(wait=True)
        self.assertRaises(OSError, lambda: os.kill(pid, 0))


class TtyCreateChildTest(unittest2.TestCase):
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
            pid, fd, _ = self.func(
                'bash', '-c', 'exec 2>%s; echo hi > /dev/tty' % (tf.name,)
            )
            deadline = time.time() + 5.0
            for line in mitogen.parent.iter_read([fd], deadline):
                self.assertEquals('hi\n', line)
                break
            waited_pid, status = os.waitpid(pid, 0)
            self.assertEquals(pid, waited_pid)
            self.assertEquals(0, status)
            self.assertEquals('', tf.read())
        finally:
            tf.close()


class IterReadTest(unittest2.TestCase):
    func = staticmethod(mitogen.parent.iter_read)

    def make_proc(self):
        args = [testlib.data_path('iter_read_generator.sh')]
        proc = subprocess.Popen(args, stdout=subprocess.PIPE)
        mitogen.core.set_nonblock(proc.stdout.fileno())
        return proc

    def test_no_deadline(self):
        proc = self.make_proc()
        try:
            reader = self.func([proc.stdout.fileno()])
            for i, chunk in enumerate(reader, 1):
                self.assertEqual(i, int(chunk))
                if i > 3:
                    break
        finally:
            proc.terminate()

    def test_deadline_exceeded_before_call(self):
        proc = self.make_proc()
        reader = self.func([proc.stdout.fileno()], 0)
        try:
            got = []
            try:
                for chunk in reader:
                    got.append(chunk)
                assert 0, 'TimeoutError not raised'
            except mitogen.core.TimeoutError:
                self.assertEqual(len(got), 0)
        finally:
            proc.terminate()

    def test_deadline_exceeded_during_call(self):
        proc = self.make_proc()
        reader = self.func([proc.stdout.fileno()], time.time() + 0.4)
        try:
            got = []
            try:
                for chunk in reader:
                    got.append(chunk)
                assert 0, 'TimeoutError not raised'
            except mitogen.core.TimeoutError:
                # Give a little wiggle room in case of imperfect scheduling.
                # Ideal number should be 9.
                self.assertLess(3, len(got))
                self.assertLess(len(got), 5)
        finally:
            proc.terminate()


class WriteAllTest(unittest2.TestCase):
    func = staticmethod(mitogen.parent.write_all)

    def make_proc(self):
        args = [testlib.data_path('write_all_consumer.sh')]
        proc = subprocess.Popen(args, stdin=subprocess.PIPE)
        mitogen.core.set_nonblock(proc.stdin.fileno())
        return proc

    ten_ms_chunk = ('x' * 65535)

    def test_no_deadline(self):
        proc = self.make_proc()
        try:
            self.func(proc.stdin.fileno(), self.ten_ms_chunk)
        finally:
            proc.terminate()

    def test_deadline_exceeded_before_call(self):
        proc = self.make_proc()
        try:
            self.assertRaises(mitogen.core.TimeoutError, (
                lambda: self.func(proc.stdin.fileno(), self.ten_ms_chunk, 0)
            ))
        finally:
            proc.terminate()

    def test_deadline_exceeded_during_call(self):
        proc = self.make_proc()
        try:
            deadline = time.time() + 0.1   # 100ms deadline
            self.assertRaises(mitogen.core.TimeoutError, (
                lambda: self.func(proc.stdin.fileno(),
                                  self.ten_ms_chunk * 100,  # 1s of data
                                  deadline)
            ))
        finally:
            proc.terminate()


if __name__ == '__main__':
    unittest2.main()
