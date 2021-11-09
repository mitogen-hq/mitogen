#!/usr/bin/env python

import ci_lib

batches = [
    [
        'pip install '
            '-r tests/requirements.txt '
            '-r tests/ansible/requirements.txt',
        # encoding is required for installing ansible 2.10 with pip2, otherwise we get a UnicodeDecode error
        'LC_CTYPE=en_US.UTF-8 LANG=en_US.UTF-8 pip install "ansible-base<2.10.14" "ansible=={}"'.format(ci_lib.ANSIBLE_VERSION)
    ],
    [
        'aws ecr-public get-login-password | docker login --username AWS --password-stdin public.ecr.aws',
    ]
]

batches[-1].extend([
    'docker pull %s' % (ci_lib.image_for_distro(distro),)
    for distro in ci_lib.DISTROS
])

ci_lib.run_batches(batches)
