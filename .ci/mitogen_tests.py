#!/usr/bin/env python
# Run the Mitogen tests.

import os

import ci_lib

os.environ.update({
    'MITOGEN_LOG_LEVEL': 'debug',
    'SKIP_ANSIBLE': '1',
})

interesting = ci_lib.get_interesting_procs()
ci_lib.run('./run_tests -v')
ci_lib.check_stray_processes(interesting)
