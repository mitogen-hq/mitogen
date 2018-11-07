#!/usr/bin/env python

import ci_lib

batches = [
    [
        'pip install "pycparser<2.19"',
        'pip install -r tests/requirements.txt',
    ],
    [
        'docker pull %s' % (ci_lib.image_for_distro(ci_lib.DISTRO),),
    ]
]

ci_lib.run_batches(batches)
