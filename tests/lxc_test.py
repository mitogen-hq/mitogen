import os

import mitogen

import unittest2

import testlib


def has_subseq(seq, subseq):
    return any(seq[x:x+len(subseq)] == subseq for x in range(0, len(seq)))


class FakeLxcAttachTest(testlib.RouterMixin, unittest2.TestCase):
    def test_okay(self):
        lxc_attach_path = testlib.data_path('fake_lxc_attach.py')
        context = self.router.lxc(
            container='container_name',
            lxc_attach_path=lxc_attach_path,
        )

        argv = eval(context.call(os.getenv, 'ORIGINAL_ARGV'))
        self.assertEquals(argv[0], lxc_attach_path)
        self.assertTrue('--clear-env' in argv)
        self.assertTrue(has_subseq(argv, ['--name', 'container_name']))


if __name__ == '__main__':
    unittest2.main()
