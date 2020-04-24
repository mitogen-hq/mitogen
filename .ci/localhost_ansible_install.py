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

# separately install ansible based on version passed in from azure-pipelines.yml or .travis.yml
batches.append("pip install -q ansible==%s", ci_lib.ANSIBLE_VERSION)

ci_lib.run_batches(batches)
