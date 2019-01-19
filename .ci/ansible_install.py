#!/usr/bin/env python

import ci_lib

batches = [
    [
        # Must be installed separately, as PyNACL indirect requirement causes
        # newer version to be installed if done in a single pip run.
        'pip install "pycparser<2.19" "idna<2.7"',
        'pip install '
            '-r tests/requirements.txt '
            '-r tests/ansible/requirements.txt',
    ]
]

batches.extend(
    ['docker pull %s' % (ci_lib.image_for_distro(distro),)]
    for distro in ci_lib.DISTROS
)

ci_lib.run_batches(batches)
