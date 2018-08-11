#!/usr/bin/env python

"""
Build the Docker images used for testing.
"""

import commands
import os
import shlex
import subprocess


BASEDIR = os.path.dirname(os.path.abspath(__file__))


def sh(s, *args):
    if args:
        s %= args
    return shlex.split(s)


for base_image, name in [('debian:stretch', 'debian'),
                         ('centos:6', 'centos6'),
                         ('centos:7', 'centos7')]:
    args = sh('docker run --rm -it -d %s /bin/bash', base_image)
    container_id = subprocess.check_output(args).strip()
    try:
        subprocess.check_call(
            cwd=BASEDIR,
            args=sh('''
                ansible-playbook -i %s, -c docker setup.yml -vvv
            ''', container_id)
        )

        subprocess.check_call(sh('''
            docker commit
            --change 'EXPOSE 22'
            --change 'CMD ["/usr/sbin/sshd", "-D"]'
            %s
            mitogen/%s-test
        ''', container_id, name))
    finally:
        subprocess.check_call(sh('docker rm -f %s', container_id))
