
import os
import shutil
import unittest

import mitogen.fakessh

import testlib


class RsyncTest(testlib.DockerMixin, unittest.TestCase):
    def test_rsync_from_master(self):
        context = self.docker_ssh_any()

        if context.call(os.path.exists, '/tmp/data'):
            context.call(shutil.rmtree, '/tmp/data')

        return_code = mitogen.fakessh.run(context, self.router, [
            'rsync', '--progress', '-vvva',
            testlib.data_path('.'), 'target:/tmp/data'
        ])

        assert return_code == 0
        assert context.call(os.path.exists, '/tmp/data')
        assert context.call(os.path.exists, '/tmp/data/simple_pkg/a.py')

