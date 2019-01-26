#!/usr/bin/env python
# Mitogen tests for Python 2.4.

import os

import ci_lib

os.environ.update({
    'NOCOVERAGE': '1',
    'UNIT2': '/usr/local/python2.4.6/bin/unit2',

    'MITOGEN_TEST_DISTRO': ci_lib.DISTRO,
    'MITOGEN_LOG_LEVEL': 'debug',
    'SKIP_ANSIBLE': '1',
})

ci_lib.run('./run_tests -v')
