#!/usr/bin/env python

import ci_lib

# Naturally DebOps only supports Debian.
ci_lib.DISTROS = ['debian']

ci_lib.run_batches([
    [
        # Must be installed separately, as PyNACL indirect requirement causes
        # newer version to be installed if done in a single pip run.
        'pip install "pycparser<2.19"',
        'pip install '
            '-qqqU '
            '-r .ci/debops_common_requirements.txt '
            'ansible==%s' % (ci_lib.ANSIBLE_VERSION,),
    ],
    [
        'docker pull %s' % (ci_lib.image_for_distro('debian'),),
    ],
])

# This should be kept in sync with the Python debops package version,
# specified in debops_common_requirements.txt
ci_lib.run('ansible-galaxy collection install debops.debops:==2.1.2')
