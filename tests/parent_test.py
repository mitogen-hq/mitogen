import os
import subprocess
import tempfile
import time

import unittest2
import testlib

import mitogen.parent


class ContextTest(testlib.RouterMixin, unittest2.TestCase):
    def test_context_shutdown(self):
        local = self.router.local()
        pid = local.call(os.getpid)
        local.shutdown(wait=True)
        self.assertRaises(OSError, lambda: os.kill(pid, 0))


class TtyCreateChildTest(unittest2.TestCase):
    func = staticmethod(mitogen.parent.tty_create_child)

    def test_dev_tty_open_succeeds(self):
        tf = tempfile.NamedTemporaryFile()
        try:
            pid, fd = self.func(
                'bash', '-c', 'exec 2>%s; echo hi > /dev/tty' % (tf.name,)
            )
            deadline = time.time() + 5.0
            for line in mitogen.parent.iter_read(fd, deadline):
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
            reader = self.func(proc.stdout.fileno())
            for i, chunk in enumerate(reader, 1):
                self.assertEqual(i, int(chunk))
                if i > 3:
                    break
        finally:
            proc.terminate()

    def test_deadline_exceeded_before_call(self):
        proc = self.make_proc()
        reader = self.func(proc.stdout.fileno(), 0)
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
        reader = self.func(proc.stdout.fileno(), time.time() + 0.4)
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
