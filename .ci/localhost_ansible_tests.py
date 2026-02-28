#!/usr/bin/env python
# Run tests/ansible/all.yml under Ansible and Ansible-Mitogen

from __future__ import print_function

import os
import subprocess
import sys

import ci_lib


with ci_lib.Fold('job_setup'):
    os.chmod(ci_lib.TESTS_SSH_PRIVATE_KEY_FILE, int('0600', 8))


with ci_lib.Fold('machine_prep'):
    # generate a new ssh key for localhost ssh
    if not os.path.exists(os.path.expanduser("~/.ssh/id_rsa")):
        subprocess.check_call("ssh-keygen -P '' -m pem -f ~/.ssh/id_rsa", shell=True)
        subprocess.check_call("cat ~/.ssh/id_rsa.pub >> ~/.ssh/authorized_keys", shell=True)
        os.chmod(os.path.expanduser('~/.ssh'), int('0700', 8))
        os.chmod(os.path.expanduser('~/.ssh/authorized_keys'), int('0600', 8))

    # also generate it for the sudo user
    if os.system("sudo [ -f ~root/.ssh/id_rsa ]") != 0:
        subprocess.check_call("sudo ssh-keygen -P '' -m pem -f ~root/.ssh/id_rsa", shell=True)
        subprocess.check_call("sudo cat ~root/.ssh/id_rsa.pub | sudo tee -a ~root/.ssh/authorized_keys", shell=True)
        subprocess.check_call('sudo chmod 700 ~root/.ssh', shell=True)
        subprocess.check_call('sudo chmod 600 ~root/.ssh/authorized_keys', shell=True)

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
