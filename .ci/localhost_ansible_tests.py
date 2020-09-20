#!/usr/bin/env python
# Run tests/ansible/all.yml under Ansible and Ansible-Mitogen

import os
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
    # generate a new ssh key for localhost ssh
    os.system("ssh-keygen -P '' -m pem -f ~/.ssh/id_rsa")
    os.system("cat ~/.ssh/id_rsa.pub >> ~/.ssh/authorized_keys")
    # also generate it for the sudo user
    os.system("sudo ssh-keygen -P '' -m pem -f /var/root/.ssh/id_rsa")
    os.system("sudo cat /var/root/.ssh/id_rsa.pub | sudo tee -a /var/root/.ssh/authorized_keys")
    os.chmod(os.path.expanduser('~/.ssh'), int('0700', 8))
    os.chmod(os.path.expanduser('~/.ssh/authorized_keys'), int('0600', 8))
    # run chmod through sudo since it's owned by root
    os.system('sudo chmod 600 /var/root/.ssh')
    os.system('sudo chmod 600 /var/root/.ssh/authorized_keys')

    if os.path.expanduser('~mitogen__user1') == '~mitogen__user1':
        os.chdir(IMAGE_PREP_DIR)
        run("ansible-playbook -c local -i localhost, _user_accounts.yml -vvv")


with ci_lib.Fold('ansible'):
    os.chdir(TESTS_DIR)
    playbook = os.environ.get('PLAYBOOK', 'all.yml')
    run('./run_ansible_playbook.py %s -l target %s -vvv',
        playbook, ' '.join(sys.argv[1:]))
