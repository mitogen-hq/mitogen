# Copyright 2017, David Wilson
#
# Redistribution and use in source and binary forms, with or without
# modification, are permitted provided that the following conditions are met:
#
# 1. Redistributions of source code must retain the above copyright notice, this
# list of conditions and the following disclaimer.
#
# 2. Redistributions in binary form must reproduce the above copyright notice,
# this list of conditions and the following disclaimer in the documentation
# and/or other materials provided with the distribution.
#
# 3. Neither the name of the copyright holder nor the names of its contributors
# may be used to endorse or promote products derived from this software without
# specific prior written permission.
#
# THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS" AND
# ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE IMPLIED
# WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE
# DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT HOLDER OR CONTRIBUTORS BE LIABLE
# FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL
# DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR
# SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER
# CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY,
# OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE
# OF THIS SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.

import json
import operator
import os
import pwd
import re
import stat
import subprocess
import time

# Prevent accidental import of an Ansible module from hanging on stdin read.
import ansible.module_utils.basic
ansible.module_utils.basic._ANSIBLE_ARGS = '{}'


class Exit(Exception):
    """
    Raised when a module exits with success.
    """
    def __init__(self, dct):
        self.dct = dct


class ModuleError(Exception):
    """
    Raised when a module voluntarily indicates failure via .fail_json().
    """
    def __init__(self, msg, dct):
        Exception.__init__(self, msg)
        self.dct = dct


def monkey_exit_json(self, **kwargs):
    """
    Replace AnsibleModule.exit_json() with something that doesn't try to kill
    the process or JSON-encode the result dictionary. Instead, cause Exit to be
    raised, with a `dct` attribute containing the successful result dictionary.
    """
    self.add_path_info(kwargs)
    kwargs.setdefault('changed', False)
    kwargs.setdefault('invocation', {
        'module_args': self.params
    })
    kwargs = ansible.module_utils.basic.remove_values(kwargs, self.no_log_values)
    self.do_cleanup_files()
    raise Exit(kwargs)


def monkey_fail_json(self, **kwargs):
    """
    Replace AnsibleModule.fail_json() with something that raises ModuleError,
    which includes a `dct` attribute.
    """
    self.add_path_info(kwargs)
    kwargs.setdefault('failed', True)
    kwargs.setdefault('invocation', {
        'module_args': self.params
    })
    kwargs = ansible.module_utils.basic.remove_values(kwargs, self.no_log_values)
    self.do_cleanup_files()
    raise ModuleError(kwargs.get('msg'), kwargs)


def run_module(module, raw_params=None, args=None):
    """
    Set up the process environment in preparation for running an Ansible
    module. This monkey-patches the Ansible libraries in various places to
    prevent it from trying to kill the process on completion, and to prevent it
    from reading sys.stdin.
    """
    if args is None:
        args = {}
    if raw_params is not None:
        args['_raw_params'] = raw_params

    ansible.module_utils.basic.AnsibleModule.exit_json = monkey_exit_json
    ansible.module_utils.basic.AnsibleModule.fail_json = monkey_fail_json
    ansible.module_utils.basic._ANSIBLE_ARGS = json.dumps({
        'ANSIBLE_MODULE_ARGS': args
    })

    try:
        mod = __import__(module, {}, {}, [''])
        # Ansible modules begin execution on import. Thus the above __import__
        # will cause either Exit or ModuleError to be raised. If we reach the
        # line below, the module did not execute and must already have been
        # imported for a previous invocation, so we need to invoke main
        # explicitly.
        mod.main()
    except (Exit, ModuleError), e:
        return json.dumps(e.dct)


def get_user_shell():
    """
    For commands executed directly via an SSH command-line, SSH looks up the
    user's shell via getpwuid() and only defaults to /bin/sh if that field is
    missing or empty.
    """
    try:
        pw_shell = pwd.getpwuid(os.geteuid()).pw_shell
    except KeyError:
        pw_shell = None

    return pw_shell or '/bin/sh'


def exec_command(cmd, in_data='', chdir=None, shell=None):
    """
    Run a command in a subprocess, emulating the argument handling behaviour of
    SSH.

    :param bytes cmd:
        String command line, passed to user's shell.
    :param bytes in_data:
        Optional standard input for the command.
    :return:
        (return code, stdout bytes, stderr bytes)
    """
    assert isinstance(cmd, basestring)

    proc = subprocess.Popen(
        args=[get_user_shell(), '-c', cmd],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        stdin=subprocess.PIPE,
        cwd=chdir,
    )
    stdout, stderr = proc.communicate(in_data)
    return proc.returncode, stdout, stderr


def read_path(path):
    """
    Fetch the contents of a filesystem `path` as bytes.
    """
    return open(path, 'rb').read()


def write_path(path, s):
    """
    Writes bytes `s` to a filesystem `path`.
    """
    open(path, 'wb').write(s)



CHMOD_CLAUSE_PAT = re.compile(r'([uoga]?)([+\-=])([ugo]|[rwx]*)')
CHMOD_MASKS = {
    'u': stat.S_IRWXU,
    'g': stat.S_IRWXG,
    'o': stat.S_IRWXO,
    'a': (stat.S_IRWXU | stat.S_IRWXG | stat.S_IRWXO),
}
CHMOD_BITS = {
    'u': {'r':stat.S_IRUSR, 'w':stat.S_IWUSR, 'x':stat.S_IXUSR},
    'g': {'r':stat.S_IRGRP, 'w':stat.S_IWGRP, 'x':stat.S_IXGRP},
    'o': {'r':stat.S_IROTH, 'w':stat.S_IWOTH, 'x':stat.S_IXOTH},
    'a': {
        'r': (stat.S_IRUSR | stat.S_IRGRP | stat.S_IROTH),
        'w': (stat.S_IWUSR | stat.S_IWGRP | stat.S_IWOTH),
        'x': (stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    }
}

def or_(it):
    return reduce(operator.or_, it, 0)


def apply_mode_spec(spec, mode):
    for clause in spec.split(','):
        match = CHMOD_CLAUSE_PAT.match(clause)
        who, op, perms = match.groups()
        mask = CHMOD_MASKS[who]
        bits = CHMOD_BITS[who]
        for ch in who or 'a':
            cur_perm_bits = mode & mask
            new_perm_bits = or_(bits[p] for p in perms)
            mode &= ~mask
            if op == '=':
                mode |= new_perm_bits
            elif op == '+':
                mode |= new_perm_bits | cur_per_bits
            else:
                mode |= cur_perm_bits & ~new_perm_bits
    return mode


def set_file_mode(path, spec):
    """
    Update the permissions of a file using the same syntax as chmod(1).
    """
    mode = os.stat(path).st_mode

    if spec.is_digit():
        new_mode = int(spec, 8)
    else:
        new_mode = apply_mode_spec(spec, mode)

    os.chmod(path, new_mode)
