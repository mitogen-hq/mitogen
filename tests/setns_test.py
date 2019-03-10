
import os
import socket

import mitogen
import mitogen.parent

import unittest2

import testlib


class DockerTest(testlib.DockerMixin, testlib.TestCase):
    def test_okay(self):
        # Magic calls must happen as root.
        try:
            root = self.router.sudo()
        except mitogen.core.StreamError:
            raise unittest2.SkipTest("requires sudo to localhost root")

        via_ssh = self.docker_ssh(
            username='mitogen__has_sudo',
            password='has_sudo_password',
        )

        via_setns = self.router.setns(
            kind='docker',
            container=self.dockerized_ssh.container_name,
            via=root,
        )

        self.assertEquals(
            via_ssh.call(socket.gethostname),
            via_setns.call(socket.gethostname),
        )

if __name__ == '__main__':
    unittest2.main()
