#!/usr/bin/env python

import ci_lib

# Naturally DebOps only supports Debian.
ci_lib.DISTROS = ['debian']

ci_lib.run_batches([
    [
        # Must be installed separately, as PyNACL indirect requirement causes
        # newer version to be installed if done in a single pip run.
        'pip install "pycparser<2.19"',
        # 'pip install -qqqU debops==0.7.2 ansible==%s' % ci_lib.ANSIBLE_VERSION,
        # ansible v2.10 isn't out yet so we're installing from github for now
        'pip install -qqqU debops==2.1.2 {}'.format(ci_lib.ANSIBLE_VERSION)
    ],
    [
        'docker pull %s' % (ci_lib.image_for_distro('debian'),),
    ],
])

# after ansible is installed, install common collections until ansible==2.10 comes out
ci_lib.run('ansible-galaxy collection install community.general')
