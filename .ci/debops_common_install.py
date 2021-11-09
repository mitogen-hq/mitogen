#!/usr/bin/env python

import ci_lib

# Naturally DebOps only supports Debian.
ci_lib.DISTROS = ['debian']

ci_lib.run_batches([
    [
        'pip install -qqq "debops[ansible]==2.1.2" "ansible-base<2.10.14" "ansible=={}"'.format(ci_lib.ANSIBLE_VERSION),
    ],
    [
        'aws ecr-public get-login-password | docker login --username AWS --password-stdin public.ecr.aws',
        'docker pull %s' % (ci_lib.image_for_distro('debian'),),
    ],
])

ci_lib.run('ansible-galaxy collection install debops.debops:==2.1.2')
