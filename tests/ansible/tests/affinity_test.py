
import multiprocessing
import os
import tempfile

import mock
import unittest2
import testlib

import mitogen.parent
import ansible_mitogen.affinity


@unittest2.skipIf(
    reason='Linux/SMP only',
    condition=(not (
        os.uname()[0] == 'Linux' and
        multiprocessing.cpu_count() >= 4
    ))
)
class LinuxPolicyTest(testlib.TestCase):
    klass = ansible_mitogen.affinity.LinuxPolicy

    def setUp(self):
        self.policy = self.klass()

    def _get_cpus(self, path='/proc/self/status'):
        fp = open(path)
        try:
            for line in fp:
                if line.startswith('Cpus_allowed'):
                    return int(line.split()[1], 16)
        finally:
            fp.close()

    def test_set_clear(self):
        before = self._get_cpus()
        self.policy._set_cpu(3)
        self.assertEquals(self._get_cpus(), 1 << 3)
        self.policy._clear()
        self.assertEquals(self._get_cpus(), before)

    def test_clear_on_popen(self):
        tf = tempfile.NamedTemporaryFile()
        try:
            before = self._get_cpus()
            self.policy._set_cpu(3)
            my_cpu = self._get_cpus()

            pid = mitogen.parent.detach_popen(
                args=['cp', '/proc/self/status', tf.name]
            )
            os.waitpid(pid, 0)

            his_cpu = self._get_cpus(tf.name)
            self.assertNotEquals(my_cpu, his_cpu)
            self.policy._clear()
        finally:
            tf.close()


if __name__ == '__main__':
    unittest2.main()
