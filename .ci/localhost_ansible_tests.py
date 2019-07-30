#!/usr/bin/env python
# Run tests/ansible/all.yml under Ansible and Ansible-Mitogen

import glob
import os
import sys

import ci_lib
from ci_lib import run


TESTS_DIR = os.path.join(ci_lib.GIT_ROOT, 'tests/ansible')
IMAGE_PREP_DIR = os.path.join(ci_lib.GIT_ROOT, 'tests/image_prep')
HOSTS_DIR = os.path.join(TESTS_DIR, 'hosts')


with ci_lib.Fold('unit_tests'):
    os.environ['SKIP_MITOGEN'] = '1'
    ci_lib.run('./run_tests -v')


with ci_lib.Fold('job_setup'):
    # Don't set -U as that will upgrade Paramiko to a non-2.6 compatible version.
    run("pip install -q ansible==%s", ci_lib.ANSIBLE_VERSION)

    os.chdir(TESTS_DIR)
    os.chmod('../data/docker/mitogen__has_sudo_pubkey.key', int('0600', 7))

    if not ci_lib.exists_in_path('sshpass'):
        run("brew install sshpass")


with ci_lib.Fold('machine_prep'):
    if os.path.expanduser('~mitogen__user1') == '~mitogen_user1':
        os.chdir(IMAGE_PREP_DIR)
        run("ansible-playbook -i localhost, _user_accounts.yml")


with ci_lib.Fold('ansible'):
    os.chdir(TESTS_DIR)
    playbook = os.environ.get('PLAYBOOK', 'all.yml')
    run('./run_ansible_playbook.py %s -l target %s',
        playbook, HOSTS_DIR, ' '.join(sys.argv[1:]))
