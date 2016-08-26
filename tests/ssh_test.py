
import unittest

import econtext
import econtext.master
import econtext.ssh
import econtext.utils

import testlib


def add(x, y):
    return x + y


class SshTest(unittest.TestCase):
    def test_okay(self):
        @econtext.utils.run_with_broker
        def test(broker):
            context = econtext.ssh.connect(broker,
                hostname='hostname',
                ssh_path=testlib.data_path('fakessh.py'))
            context.call(econtext.utils.log_to_file, '/tmp/log')
            context.call(econtext.utils.disable_site_packages)
            self.assertEquals(3, context.call(add, 1, 2))
