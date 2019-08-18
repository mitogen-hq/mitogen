#!/usr/bin/env python
# Run tests/ansible/all.yml under Ansible and Ansible-Mitogen

import glob
import os
import shutil
import sys

import ci_lib
from ci_lib import run


TESTS_DIR = os.path.join(ci_lib.GIT_ROOT, 'tests/ansible')
IMAGE_PREP_DIR = os.path.join(ci_lib.GIT_ROOT, 'tests/image_prep')
HOSTS_DIR = os.path.join(TESTS_DIR, 'hosts')
KEY_PATH = os.path.join(TESTS_DIR, '../data/docker/mitogen__has_sudo_pubkey.key')


with ci_lib.Fold('unit_tests'):
    os.environ['SKIP_MITOGEN'] = '1'
    ci_lib.run('./run_tests -v')


with ci_lib.Fold('job_setup'):
    # Don't set -U as that will upgrade Paramiko to a non-2.6 compatible version.
    run("pip install -q virtualenv ansible==%s", ci_lib.ANSIBLE_VERSION)

    os.chmod(KEY_PATH, int('0600', 8))
    if not ci_lib.exists_in_path('sshpass'):
        run("brew install http://git.io/sshpass.rb")


with ci_lib.Fold('machine_prep'):
    ssh_dir = os.path.expanduser('~/.ssh')
    if not os.path.exists(ssh_dir):
        os.makedirs(ssh_dir, int('0700', 8))

    key_path = os.path.expanduser('~/.ssh/id_rsa')
    shutil.copy(KEY_PATH, key_path)

    auth_path = os.path.expanduser('~/.ssh/authorized_keys')
    os.system('ssh-keygen -y -f %s >> %s' % (key_path, auth_path))
    os.chmod(auth_path, int('0600', 8))

    if os.path.expanduser('~mitogen__user1') == '~mitogen__user1':
        os.chdir(IMAGE_PREP_DIR)
        run("ansible-playbook -c local -i localhost, _user_accounts.yml")


with ci_lib.Fold('ansible'):
    os.chdir(TESTS_DIR)
    playbook = os.environ.get('PLAYBOOK', 'all.yml')
    run('./run_ansible_playbook.py %s -l target %s',
        playbook, ' '.join(sys.argv[1:]))
