#!/usr/bin/env python

import ci_lib

# Naturally DebOps only supports Debian.
ci_lib.DISTROS = ['debian']

ci_lib.run_batches([
    [
        'python -m pip --no-python-version-warning --disable-pip-version-check "debops[ansible]==2.1.2"',
    ],
    [
        'aws ecr-public get-login-password | docker login --username AWS --password-stdin public.ecr.aws',
    ],
])

ci_lib.run('ansible-galaxy collection install debops.debops:==2.1.2')
