#!/usr/bin/env python

import ci_lib

ci_lib.run_batches([
    [
        'python -m pip --no-python-version-warning --disable-pip-version-check "debops[ansible]==2.1.2"',
    ],
])

ci_lib.run('ansible-galaxy collection install debops.debops:==2.1.2')
