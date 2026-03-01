#!/usr/bin/env python
# Run tests/ansible/all.yml under Ansible and Ansible-Mitogen

from __future__ import print_function

import os
import sys

import ci_lib


with ci_lib.Fold('unit_tests'):
    os.environ['SKIP_MITOGEN'] = '1'
    ci_lib.run('./run_tests -v')


with ci_lib.Fold('ansible'):
    os.chdir(ci_lib.ANSIBLE_TESTS_DIR)
    playbook = os.environ.get('PLAYBOOK', 'all.yml')
    ci_lib.run('./run_ansible_playbook.py %s %s',
        playbook, ' '.join(sys.argv[1:]))
