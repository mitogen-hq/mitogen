#!/usr/bin/env python
# Run the Mitogen tests.

import os
import subprocess

import ci_lib

os.environ.update({
    'MITOGEN_LOG_LEVEL': 'debug',
    'SKIP_ANSIBLE': '1',
})

if not ci_lib.have_docker():
    os.environ['SKIP_DOCKER_TESTS'] = '1'

subprocess.check_call(
    "umask 0022; sudo cp '%s' '%s'"
    % (ci_lib.SUDOERS_DEFAULTS_SRC, ci_lib.SUDOERS_DEFAULTS_DEST),
    shell=True,
)
subprocess.check_call(['sudo', 'visudo', '-cf', ci_lib.SUDOERS_DEFAULTS_DEST])
subprocess.check_call(['sudo', '-l'])

interesting = ci_lib.get_interesting_procs()
ci_lib.run('./run_tests -v')
ci_lib.check_stray_processes(interesting)
