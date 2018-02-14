
import subprocess
import time

import unittest2

import testlib
import mitogen.master
import mitogen.parent


class ScanCodeImportsTest(unittest2.TestCase):
    func = staticmethod(mitogen.master.scan_code_imports)

    def test_simple(self):
        co = compile(open(__file__).read(), __file__, 'exec')
        self.assertEquals(list(self.func(co)), [
            (-1, 'subprocess', ()),
            (-1, 'time', ()),
            (-1, 'unittest2', ()),
            (-1, 'testlib', ()),
            (-1, 'mitogen.master', ()),
            (-1, 'mitogen.parent', ()),
        ])


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
