
import unittest

import mitogen
import mitogen.master
import mitogen.ssh
import mitogen.utils

import testlib


def add(x, y):
    return x + y


class SshTest(unittest.TestCase):
    def test_okay(self):
        @mitogen.utils.run_with_broker
        def test(broker):
            context = mitogen.ssh.connect(broker,
                hostname='hostname',
                ssh_path=testlib.data_path('fakessh.py'))
            context.call(mitogen.utils.log_to_file, '/tmp/log')
            context.call(mitogen.utils.disable_site_packages)
            self.assertEquals(3, context.call(add, 1, 2))
