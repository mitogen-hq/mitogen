#!/usr/bin/env python

import ci_lib

batches = [
    [
        'pip install '
            '-r tests/requirements.txt '
            '-r tests/ansible/requirements.txt',
        'pip install -q "ansible-base<2.10.14" "ansible=={}"'.format(ci_lib.ANSIBLE_VERSION)
    ]
]

ci_lib.run_batches(batches)
