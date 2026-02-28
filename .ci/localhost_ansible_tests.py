#!/usr/bin/env python
# Run tests/ansible/all.yml under Ansible and Ansible-Mitogen

from __future__ import print_function

import os
import sys

import ci_lib


with ci_lib.Fold('machine_prep'):
    os.chdir(ci_lib.IMAGE_PREP_DIR)

    if os.path.expanduser('~mitogen__user1') == '~mitogen__user1':
        os.chdir(ci_lib.IMAGE_PREP_DIR)
        ci_lib.run("ansible-playbook -c local -i localhost, _user_accounts.yml")

    ci_lib.run("ansible-playbook -c local -i localhost, macos_localhost.yml")

with ci_lib.Fold('ansible'):
    os.chdir(ci_lib.ANSIBLE_TESTS_DIR)
    playbook = os.environ.get('PLAYBOOK', 'all.yml')
    ci_lib.run('./run_ansible_playbook.py %s %s',
        playbook, ' '.join(sys.argv[1:]))
