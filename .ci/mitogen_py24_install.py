#!/usr/bin/env python

import ci_lib

batches = [
    [
        'docker pull %s' % (ci_lib.image_for_distro(ci_lib.DISTRO),),
    ],
    [
        'sudo tar -C / -jxvf tests/data/ubuntu-python-2.4.6.tar.bz2',
    ]
]

ci_lib.run_batches(batches)
