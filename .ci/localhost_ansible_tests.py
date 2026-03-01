#!/usr/bin/env python
# Run tests/ansible/all.yml under Ansible and Ansible-Mitogen

from __future__ import print_function

import os
import subprocess
import sys

import ci_lib


with ci_lib.Fold('unit_tests'):
    os.environ['SKIP_MITOGEN'] = '1'
    ci_lib.run('./run_tests -v')


with ci_lib.Fold('machine_prep'):
    os.chdir(ci_lib.IMAGE_PREP_DIR)

    if os.path.expanduser('~mitogen__user1') == '~mitogen__user1':
        os.chdir(ci_lib.IMAGE_PREP_DIR)
        ci_lib.run("ansible-playbook -c local -i localhost, _user_accounts.yml")

    ci_lib.run("ansible-playbook -c local -i localhost, macos_localhost.yml")

    cmd = ';'.join([
        'from __future__ import print_function',
        'import os, sys',
        'print(sys.executable, os.path.realpath(sys.executable))',
    ])
    for interpreter in ['/usr/bin/python', '/usr/bin/python2', '/usr/bin/python2.7']:
        print(interpreter)
        try:
            subprocess.call([interpreter, '-c', cmd])
        except OSError as exc:
            print(exc)

        print(interpreter, 'with PYTHON_LAUNCHED_FROM_WRAPPER=1')
        environ = os.environ.copy()
        environ['PYTHON_LAUNCHED_FROM_WRAPPER'] = '1'
        try:
            subprocess.call([interpreter, '-c', cmd], env=environ)
        except OSError as exc:
            print(exc)


with ci_lib.Fold('ansible'):
    os.chdir(ci_lib.ANSIBLE_TESTS_DIR)
    playbook = os.environ.get('PLAYBOOK', 'all.yml')
    ci_lib.run('./run_ansible_playbook.py %s %s',
        playbook, ' '.join(sys.argv[1:]))
