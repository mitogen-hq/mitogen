#!/usr/bin/env python
# Wrap ansible-playbook, setting up some test of the test environment.

import json
import os
import sys


# Used by delegate_to.yml to ensure "sudo -E" preserves environment.
os.environ['I_WAS_PRESERVED'] = '1'

# Used by LRU tests.
os.environ['MITOGEN_MAX_INTERPRETERS'] = '3'

extra = {
    'is_mitogen': os.environ.get('ANSIBLE_STRATEGY', '').startswith('mitogen'),
    'git_basedir': os.path.dirname(
        os.path.abspath(
            os.path.join(__file__, '..', '..')
        )
    )
}

args = ['ansible-playbook']
args += ['-e', json.dumps(extra)]
args += sys.argv[1:]
os.execvp(args[0], args)
