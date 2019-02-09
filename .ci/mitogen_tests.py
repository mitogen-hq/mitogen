#!/usr/bin/env python
# Run the Mitogen tests.

import os

import ci_lib

os.environ.update({
    'MITOGEN_TEST_DISTRO': ci_lib.DISTRO,
    'MITOGEN_LOG_LEVEL': 'debug',
    'SKIP_ANSIBLE': '1',
})

ci_lib.run('./run_tests -v')
ci_lib.run('coveralls')
