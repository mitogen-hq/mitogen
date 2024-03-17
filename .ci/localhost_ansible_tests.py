#!/usr/bin/env python
# Run tests/ansible/all.yml under Ansible and Ansible-Mitogen

from __future__ import print_function

import getpass
import io
import os
import subprocess
import sys

import ci_lib


TESTS_DIR = os.path.join(ci_lib.GIT_ROOT, 'tests/ansible')
IMAGE_PREP_DIR = os.path.join(ci_lib.GIT_ROOT, 'tests/image_prep')
HOSTS_DIR = os.path.join(TESTS_DIR, 'hosts')
KEY_PATH = os.path.join(TESTS_DIR, '../data/docker/mitogen__has_sudo_pubkey.key')


with ci_lib.Fold('unit_tests'):
    os.environ['SKIP_MITOGEN'] = '1'
    ci_lib.run('./run_tests -v')


with ci_lib.Fold('job_setup'):
    os.chmod(KEY_PATH, int('0600', 8))
    # NOTE: sshpass v1.06 causes errors so pegging to 1.05 -> "msg": "Error when changing password","out": "passwd: DS error: eDSAuthFailed\n", 
    # there's a checksum error with "brew install http://git.io/sshpass.rb" though, so installing manually
    if not ci_lib.exists_in_path('sshpass'):
        subprocess.check_call(
                "curl -O -L  https://sourceforge.net/projects/sshpass/files/sshpass/1.05/sshpass-1.05.tar.gz && \
                tar xvf sshpass-1.05.tar.gz && \
                cd sshpass-1.05 && \
                ./configure && \
                sudo make install",
                shell=True,
        )


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

    if os.path.expanduser('~mitogen__user1') == '~mitogen__user1':
        os.chdir(IMAGE_PREP_DIR)
        ci_lib.run("ansible-playbook -c local -i localhost, _user_accounts.yml")

    # FIXME Don't hardcode https://github.com/mitogen-hq/mitogen/issues/1022
    #       and os.environ['USER'] is not populated on Azure macOS runners.
    os.chdir(HOSTS_DIR)
    with io.open('default.hosts', 'r+', encoding='utf-8') as f:
        user = getpass.getuser()
        content = f.read()
        content = content.replace("{{ lookup('pipe', 'whoami') }}", user)
        f.seek(0)
        f.write(content)
        f.truncate()
    ci_lib.dump_file('default.hosts')

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
    os.chdir(TESTS_DIR)
    playbook = os.environ.get('PLAYBOOK', 'all.yml')
    ci_lib.run('./run_ansible_playbook.py %s -l target %s',
        playbook, ' '.join(sys.argv[1:]))
