import multiprocessing
import os
import sys
import tempfile
import unittest

import testlib

import mitogen.parent
import ansible_mitogen.affinity



class NullFixedPolicy(ansible_mitogen.affinity.FixedPolicy):
    def _set_cpu_mask(self, mask):
        self.mask = mask


@unittest.skipIf(
    reason='Linux only',
    condition=(not os.uname()[0] == 'Linux')
)
class FixedPolicyTest(testlib.TestCase):
    klass = NullFixedPolicy

    def test_assign_controller_1core(self):
        # Uniprocessor .
        policy = self.klass(cpu_count=1)
        policy.assign_controller()
        self.assertEqual(0x1, policy.mask)

    def test_assign_controller_2core(self):
        # Small SMP gets 1.. % cpu_count
        policy = self.klass(cpu_count=2)
        policy.assign_controller()
        self.assertEqual(0x2, policy.mask)
        policy.assign_controller()
        self.assertEqual(0x2, policy.mask)
        policy.assign_controller()

    def test_assign_controller_3core(self):
        # Small SMP gets 1.. % cpu_count
        policy = self.klass(cpu_count=3)
        policy.assign_controller()
        self.assertEqual(0x2, policy.mask)
        policy.assign_controller()
        self.assertEqual(0x4, policy.mask)
        policy.assign_controller()
        self.assertEqual(0x2, policy.mask)
        policy.assign_controller()
        self.assertEqual(0x4, policy.mask)
        policy.assign_controller()

    def test_assign_controller_4core(self):
        # Big SMP gets a dedicated core.
        policy = self.klass(cpu_count=4)
        policy.assign_controller()
        self.assertEqual(0x2, policy.mask)
        policy.assign_controller()
        self.assertEqual(0x2, policy.mask)

    def test_assign_muxprocess_1core(self):
        # Uniprocessor .
        policy = self.klass(cpu_count=1)
        policy.assign_muxprocess(0)
        self.assertEqual(0x1, policy.mask)

    def test_assign_muxprocess_2core(self):
        # Small SMP gets dedicated core.
        policy = self.klass(cpu_count=2)
        policy.assign_muxprocess(0)
        self.assertEqual(0x1, policy.mask)
        policy.assign_muxprocess(0)
        self.assertEqual(0x1, policy.mask)
        policy.assign_muxprocess(0)

    def test_assign_muxprocess_3core(self):
        # Small SMP gets a dedicated core.
        policy = self.klass(cpu_count=3)
        policy.assign_muxprocess(0)
        self.assertEqual(0x1, policy.mask)
        policy.assign_muxprocess(0)
        self.assertEqual(0x1, policy.mask)

    def test_assign_muxprocess_4core(self):
        # Big SMP gets a dedicated core.
        policy = self.klass(cpu_count=4)
        policy.assign_muxprocess(0)
        self.assertEqual(0x1, policy.mask)
        policy.assign_muxprocess(0)
        self.assertEqual(0x1, policy.mask)

    def test_assign_worker_1core(self):
        # Balance n % 1
        policy = self.klass(cpu_count=1)
        policy.assign_worker()
        self.assertEqual(0x1, policy.mask)
        policy.assign_worker()
        self.assertEqual(0x1, policy.mask)

    def test_assign_worker_2core(self):
        # Balance n % 1
        policy = self.klass(cpu_count=2)
        policy.assign_worker()
        self.assertEqual(0x2, policy.mask)
        policy.assign_worker()
        self.assertEqual(0x2, policy.mask)

    def test_assign_worker_3core(self):
        # Balance n % 1
        policy = self.klass(cpu_count=3)
        policy.assign_worker()
        self.assertEqual(0x2, policy.mask)
        policy.assign_worker()
        self.assertEqual(0x4, policy.mask)
        policy.assign_worker()
        self.assertEqual(0x2, policy.mask)

    def test_assign_worker_4core(self):
        # Balance n % 1
        policy = self.klass(cpu_count=4)
        policy.assign_worker()
        self.assertEqual(4, policy.mask)
        policy.assign_worker()
        self.assertEqual(8, policy.mask)
        policy.assign_worker()
        self.assertEqual(4, policy.mask)

    def test_assign_subprocess_1core(self):
        # allow all except reserved.
        policy = self.klass(cpu_count=1)
        policy.assign_subprocess()
        self.assertEqual(0x1, policy.mask)
        policy.assign_subprocess()
        self.assertEqual(0x1, policy.mask)

    def test_assign_subprocess_2core(self):
        # allow all except reserved.
        policy = self.klass(cpu_count=2)
        policy.assign_subprocess()
        self.assertEqual(0x2, policy.mask)
        policy.assign_subprocess()
        self.assertEqual(0x2, policy.mask)

    def test_assign_subprocess_3core(self):
        # allow all except reserved.
        policy = self.klass(cpu_count=3)
        policy.assign_subprocess()
        self.assertEqual(0x2 + 0x4, policy.mask)
        policy.assign_subprocess()
        self.assertEqual(0x2 + 0x4, policy.mask)

    def test_assign_subprocess_4core(self):
        # allow all except reserved.
        policy = self.klass(cpu_count=4)
        policy.assign_subprocess()
        self.assertEqual(0x4 + 0x8, policy.mask)
        policy.assign_subprocess()
        self.assertEqual(0x4 + 0x8, policy.mask)


@unittest.skipIf(
    reason='Linux/SMP only',
    condition=(not (
        os.uname()[0] == 'Linux' and
        multiprocessing.cpu_count() > 2
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
                    mask = line.split()[1].replace(',', '')
                    return int(mask, 16)
        finally:
            fp.close()

    def test_set_cpu_mask(self):
        self.policy._set_cpu_mask(0x1)
        self.assertEqual(0x1, self._get_cpus())

        self.policy._set_cpu_mask(0x2)
        self.assertEqual(0x2, self._get_cpus())

        self.policy._set_cpu_mask(0x3)
        self.assertEqual(0x3, self._get_cpus())

    def test_clear_on_popen(self):
        tf = tempfile.NamedTemporaryFile()
        try:
            before = self._get_cpus()
            self.policy._set_cpu(None, 3)
            my_cpu = self._get_cpus()

            proc = mitogen.parent.popen(
                args=['cp', '/proc/self/status', tf.name]
            )
            proc.wait()

            his_cpu = self._get_cpus(tf.name)
            self.assertNotEquals(my_cpu, his_cpu)
            self.policy._clear()
        finally:
            tf.close()


class MockLinuxPolicyTest(testlib.TestCase):
    klass = ansible_mitogen.affinity.LinuxPolicy

    # Test struct.pack() in _set_cpu_mask().

    def test_high_cpus(self):
        policy = self.klass(cpu_count=4096)
        for x in range(1, 4096, 32):
            policy.assign_subprocess()

MockLinuxPolicyTest = unittest.skipIf(
    condition=(not sys.platform.startswith('linuxPolicy')),
    reason='select.select() not supported'
)(MockLinuxPolicyTest)
