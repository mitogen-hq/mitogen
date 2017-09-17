
import os
import shutil
import unittest

import mitogen.utils
import mitogen.fakessh

import testlib


class RsyncTest(testlib.DockerMixin, unittest.TestCase):
    def test_rsync_from_master(self):
        context = self.docker_ssh_any()
        context.call(shutil.rmtree, '/tmp/data', ignore_errors=True)
        mitogen.fakessh.run(context, self.router, [
            'rsync', '--progress', '-vvva',
            testlib.data_path('.'), 'target:/tmp/data'
        ])
        assert context.call(os.path.exists, '/tmp/data')
        assert context.call(os.path.exists, '/tmp/data/simple_pkg/a.py')

