
import os
import socket
import sys

import mitogen
import mitogen.parent

import unittest2

import testlib


# TODO: https://github.com/dw/mitogen/issues/688 https://travis-ci.org/github/dw/mitogen/jobs/665088918?utm_medium=notification&utm_source=github_status
# class DockerTest(testlib.DockerMixin, testlib.TestCase):
#     def test_okay(self):
#         # Magic calls must happen as root.
#         try:
#             root = self.router.sudo()
#         except mitogen.core.StreamError:
#             raise unittest2.SkipTest("requires sudo to localhost root")

#         via_ssh = self.docker_ssh(
#             username='mitogen__has_sudo',
#             password='has_sudo_password',
#         )

#         via_setns = self.router.setns(
#             kind='docker',
#             container=self.dockerized_ssh.container_name,
#             via=root,
#         )

#         self.assertEquals(
#             via_ssh.call(socket.gethostname),
#             via_setns.call(socket.gethostname),
#         )


# DockerTest = unittest2.skipIf(
#     condition=sys.version_info < (2, 5),
#     reason="mitogen.setns unsupported on Python <2.4"
# )(DockerTest)


# if __name__ == '__main__':
#     unittest2.main()
