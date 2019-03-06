#!/usr/bin/env python

import ci_lib

batches = [
    [
        'pip install "pycparser<2.19" "idna<2.7"',
        'pip install -r tests/requirements.txt',
    ]
]

if ci_lib.have_docker():
    batches.append([
        'docker pull %s' % (ci_lib.image_for_distro(ci_lib.DISTRO),),
    ])

ci_lib.run_batches(batches)
