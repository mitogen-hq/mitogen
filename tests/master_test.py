
import subprocess
import time
import unittest

import testlib
import mitogen.master


class IterReadTest(unittest.TestCase):
    func = staticmethod(mitogen.master.iter_read)

    def make_proc(self):
        args = [testlib.data_path('iter_read_generator.sh')]
        return subprocess.Popen(args, stdout=subprocess.PIPE)

    def test_no_deadline(self):
        proc = self.make_proc()
        try:
            reader = self.func(proc.stdout.fileno())
            for i, chunk in enumerate(reader, 1):
                assert i == int(chunk)
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
                assert len(got) == 0
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
                assert 3 < len(got) < 5
        finally:
            proc.terminate()
