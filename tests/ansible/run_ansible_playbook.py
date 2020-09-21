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

# Ensure VIRTUAL_ENV is exported.
os.environ.setdefault(
    'VIRTUAL_ENV',
    os.path.dirname(os.path.dirname(sys.executable))
)

# Set LANG and LC_ALL to C in order to avoid locale errors spammed by vanilla
# during exec_command().
os.environ.pop('LANG', None)
os.environ.pop('LC_ALL', None)


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

if '-i' in sys.argv:
    extra['MITOGEN_INVENTORY_FILE'] = (
        os.path.abspath(sys.argv[1 + sys.argv.index('-i')])
    )
else:
    extra['MITOGEN_INVENTORY_FILE'] = (
        os.path.join(GIT_BASEDIR, 'tests/ansible/hosts')
    )

if 'ANSIBLE_ARGV' in os.environ:
    args = eval(os.environ['ANSIBLE_ARGV'])
else:
    args = ['ansible-playbook']

args += ['-e', json.dumps(extra)]
args += sys.argv[1:]
os.execvp(args[0], args)
