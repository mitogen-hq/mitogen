#!/usr/bin/env python
import os
import sys
os.environ['ANSIBLE_STRATEGY'] = 'mitogen_linear'
os.execlp(
    './run_ansible_playbook.py',
    './run_ansible_playbook.py',
    *sys.argv[1:]
)
