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


def exec_command(cmd, in_data=''):
    """
    Run a command in subprocess, arranging for `in_data` to be supplied on its
    standard input.

    :return:
        (return code, stdout bytes, stderr bytes)
    """
    proc = subprocess.Popen(cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        stdin=subprocess.PIPE,
        shell=True)
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
