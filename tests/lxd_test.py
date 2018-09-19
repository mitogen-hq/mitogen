import os

import mitogen

import unittest2

import testlib


class FakeLxcTest(testlib.RouterMixin, unittest2.TestCase):
    def test_okay(self):
        lxc_path = testlib.data_path('fake_lxc.py')
        context = self.router.lxd(
            container='container_name',
            lxc_path=lxc_path,
        )

        argv = eval(context.call(os.getenv, 'ORIGINAL_ARGV'))
        self.assertEquals(argv[0], lxc_path)
        self.assertEquals(argv[1], 'exec')
        self.assertEquals(argv[2], '--mode=noninteractive')
        self.assertEquals(argv[3], 'container_name')


if __name__ == '__main__':
    unittest2.main()
