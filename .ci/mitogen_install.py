#!/usr/bin/env python

import ci_lib

batches = [
    [
        'pip install "pycparser<2.19"',
        'pip install -r tests/requirements.txt',
    ],
    [
        'docker pull mitogen/%s-test' % (ci_lib.DISTRO,),
    ]
]

ci_lib.run_batches(batches)
