
import os
import shutil

import unittest2

import mitogen.fakessh

import testlib


import logging
logging.basicConfig(level=logging.DEBUG)
class ExitStatusTest(testlib.RouterMixin, unittest2.TestCase):
    # Ensure child's exit status is propagated to the parent.
    def test_exit_0(self):
        local = self.router.local()

        exit_status = mitogen.fakessh.run(local, self.router, [
            'bash', '-c', 'exec ssh foo exit 0'
        ])
        self.assertEquals(0, exit_status)


class RsyncTest(testlib.DockerMixin, unittest2.TestCase):
    def test_rsync_from_master(self):
        context = self.docker_ssh_any()

        if context.call(os.path.exists, '/tmp/data'):
            context.call(shutil.rmtree, '/tmp/data')

        return_code = mitogen.fakessh.run(context, self.router, [
            'rsync', '-a',
            testlib.data_path('.'), 'target:/tmp/data'
        ])

        self.assertEqual(return_code, 0)
        self.assertTrue(context.call(os.path.exists, '/tmp/data'))
        self.assertTrue(context.call(os.path.exists, '/tmp/data/simple_pkg/a.py'))

    def test_rsync_between_direct_children(self):
        # master -> SSH -> has-sudo-pubkey -> rsync(.ssh) -> master ->
        # has-sudo -> rsync

        pubkey_acct = self.docker_ssh(
            username='has-sudo-pubkey',
            identity_file=testlib.data_path('docker/has-sudo-pubkey.key'),
        )

        nopw_acct = self.docker_ssh(
            username='has-sudo-nopw',
            password='y',
        )

        webapp_acct = self.router.sudo(
            via=nopw_acct,
            username='webapp',
        )

        dest_path = webapp_acct.call(os.path.expanduser, '~/.ssh')
        if webapp_acct.call(os.path.exists, dest_path):
            webapp_acct.call(shutil.rmtree, dest_path)

        return_code = pubkey_acct.call(mitogen.fakessh.run, webapp_acct, args=[
            'rsync', '-a', '.ssh/', 'target:' + dest_path
        ])

        self.assertEqual(return_code, 0)
        self.assertEqual(
            pubkey_acct.call(os.path.getsize, '.ssh/authorized_keys'),
            webapp_acct.call(os.path.getsize, dest_path + '/authorized_keys'),
        )


if __name__ == '__main__':
    unittest2.main()
