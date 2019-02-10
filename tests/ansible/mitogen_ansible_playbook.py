#!/usr/bin/env python
import os
import subprocess
import sys
os.environ['ANSIBLE_STRATEGY'] = 'mitogen_linear'
subprocess.check_call(['./run_ansible_playbook.py'] + sys.argv[1:])
