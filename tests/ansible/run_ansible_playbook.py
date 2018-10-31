#!/usr/bin/env python
# Wrap ansible-playbook, setting up some test of the test environment.

import json
import os
import sys


GIT_BASEDIR = os.path.dirname(
    os.path.abspath(
        os.path.join(__file__, '..', '..')
    )
)


# Used by delegate_to.yml to ensure "sudo -E" preserves environment.
os.environ['I_WAS_PRESERVED'] = '1'

# Used by LRU tests.
os.environ['MITOGEN_MAX_INTERPRETERS'] = '3'

# Add test stubs to path.
os.environ['PATH'] = '%s%s%s' % (
    os.path.join(GIT_BASEDIR, 'tests', 'data', 'stubs'),
    os.pathsep,
    os.environ['PATH'],
)

extra = {
    'is_mitogen': os.environ.get('ANSIBLE_STRATEGY', '').startswith('mitogen'),
    'git_basedir': GIT_BASEDIR,
}

args = ['ansible-playbook']
args += ['-e', json.dumps(extra)]
args += sys.argv[1:]
os.execvp(args[0], args)
