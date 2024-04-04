import unittest

import ansible_mitogen.utils


class AnsibleVersionTest(unittest.TestCase):
    def test_ansible_version(self):
        self.assertIsInstance(ansible_mitogen.utils.ansible_version, tuple)
        self.assertIsInstance(ansible_mitogen.utils.ansible_version[0], int)
        self.assertIsInstance(ansible_mitogen.utils.ansible_version[1], int)
        self.assertEqual(2, ansible_mitogen.utils.ansible_version[0])
