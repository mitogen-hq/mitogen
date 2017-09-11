"""
Ansible is so poorly layered that attempting to import anything under
ansible.plugins automatically triggers import of __main__, which causes
remote execution of the ansible command-line tool. :(

So here we define helpers in some sanely layered package where the entirety of
Ansible won't be imported.
"""

import subprocess


def exec_command(cmd, in_data=None):
    proc = subprocess.Popen(cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        stdin=subprocess.PIPE,
        shell=True)
    stdout, stderr = proc.communicate(in_data)
    return proc.returncode, stdout, stderr


def read_path(path):
    return file(path, 'rb').read()


def write_path(path, s):
    open(path, 'wb').write(s)
