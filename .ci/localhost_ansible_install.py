#!/usr/bin/env python

import ci_lib

batches = [
    [
        # Must be installed separately, as PyNACL indirect requirement causes
        # newer version to be installed if done in a single pip run.
        # Separately install ansible based on version passed in from azure-pipelines.yml or .travis.yml
        # Don't set -U as that will upgrade Paramiko to a non-2.6 compatible version.
        'pip install "pycparser<2.19" "idna<2.7" virtualenv',
        'pip install '
            '-r tests/requirements.txt '
            '-r tests/ansible/requirements.txt',
        'pip install -q ansible=={}'.format(ci_lib.ANSIBLE_VERSION)
    ]
]

ci_lib.run_batches(batches)
