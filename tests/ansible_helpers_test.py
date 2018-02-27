
import unittest2

import ansible_mitogen.helpers
import testlib


class ApplyModeSpecTest(unittest2.TestCase):
    func = staticmethod(ansible_mitogen.apply_mode_spec)

    def test_simple(self):
        spec = 'u+rwx,go=x'
        self.assertEquals(0711, self.func(spec, 0))

        spec = 'g-rw'
        self.assertEquals(0717, self.func(spec, 0777))


if __name__ == '__main__':
    unittest2.main()
