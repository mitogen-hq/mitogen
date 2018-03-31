# Copyright 2017, David Wilson
#
# Redistribution and use in source and binary forms, with or without
# modification, are permitted provided that the following conditions are met:
#
# 1. Redistributions of source code must retain the above copyright notice,
# this list of conditions and the following disclaimer.
#
# 2. Redistributions in binary form must reproduce the above copyright notice,
# this list of conditions and the following disclaimer in the documentation
# and/or other materials provided with the distribution.
#
# 3. Neither the name of the copyright holder nor the names of its contributors
# may be used to endorse or promote products derived from this software without
# specific prior written permission.
#
# THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS"
# AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE
# IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE
# ARE DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT HOLDER OR CONTRIBUTORS BE
# LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR
# CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF
# SUBSTITUTE GOODS OR SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS
# INTERRUPTION) HOWEVER CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN
# CONTRACT, STRICT LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE)
# ARISING IN ANY WAY OUT OF THE USE OF THIS SOFTWARE, EVEN IF ADVISED OF THE
# POSSIBILITY OF SUCH DAMAGE.

from __future__ import absolute_import
import json
import operator
import os
import pwd
import random
import re
import stat
import subprocess
import tempfile
import threading

import mitogen.core
import ansible_mitogen.runner

#: Mapping of job_id<->result dict
_result_by_job_id = {}

#: Mapping of job_id<->threading.Thread
_thread_by_job_id = {}


def run_module(kwargs):
    """
    Set up the process environment in preparation for running an Ansible
    module. This monkey-patches the Ansible libraries in various places to
    prevent it from trying to kill the process on completion, and to prevent it
    from reading sys.stdin.
    """
    runner_name = kwargs.pop('runner_name')
    klass = getattr(ansible_mitogen.runner, runner_name)
    impl = klass(**kwargs)
    return json.dumps(impl.run())


def _async_main(job_id, runner_name, kwargs):
    """
    Implementation for the thread that implements asynchronous module
    execution.
    """
    try:
        rc = run_module(runner_name, kwargs)
    except Exception, e:
        rc = mitogen.core.CallError(e)

    _result_by_job_id[job_id] = rc


def make_temp_directory(base_dir):
    """
    Handle creation of `base_dir` if it is absent, in addition to a unique
    temporary directory within `base_dir`.

    :returns:
        Newly created temporary directory.
    """
    if not os.path.exists(base_dir):
        os.makedirs(base_dir, mode=int('0700', 8))
    return tempfile.mkdtemp(
        dir=base_dir,
        prefix='ansible-mitogen-tmp-',
    )

def run_module_async(runner_name, kwargs):
    """
    Arrange for an Ansible module to be executed in a thread of the current
    process, with results available via :py:func:`get_async_result`.
    """
    job_id = '%08x' % random.randint(0, 2**32-1)
    _result_by_job_id[job_id] = None
    _thread_by_job_id[job_id] = threading.Thread(
        target=_async_main,
        kwargs={
            'job_id': job_id,
            'runner_name': runner_name,
            'kwargs': kwargs,
        }
    )
    _thread_by_job_id[job_id].start()
    return json.dumps({
        'ansible_job_id': job_id,
        'changed': True
    })


def get_async_result(job_id):
    """
    Poll for the result of an asynchronous task.

    :param str job_id:
        Job ID to poll for.
    :returns:
        ``None`` if job is still running, JSON-encoded result dictionary if
        execution completed normally, or :py:class:`mitogen.core.CallError` if
        an exception was thrown.
    """
    if not _thread_by_job_id[job_id].isAlive():
        return _result_by_job_id[job_id]


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


def exec_args(args, in_data='', chdir=None, shell=None):
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
        args=args,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        stdin=subprocess.PIPE,
        cwd=chdir,
    )
    stdout, stderr = proc.communicate(in_data)
    return proc.returncode, stdout, stderr


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
    return _exec_command(
        args=[get_user_shell(), '-c', cmd],
        in_data=in_Data,
        chdir=chdir,
        shell=shell,
    )


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


CHMOD_CLAUSE_PAT = re.compile(r'([uoga]*)([+\-=])([ugo]|[rwx]*)')
CHMOD_MASKS = {
    'u': stat.S_IRWXU,
    'g': stat.S_IRWXG,
    'o': stat.S_IRWXO,
    'a': (stat.S_IRWXU | stat.S_IRWXG | stat.S_IRWXO),
}
CHMOD_BITS = {
    'u': {'r': stat.S_IRUSR, 'w': stat.S_IWUSR, 'x': stat.S_IXUSR},
    'g': {'r': stat.S_IRGRP, 'w': stat.S_IWGRP, 'x': stat.S_IXGRP},
    'o': {'r': stat.S_IROTH, 'w': stat.S_IWOTH, 'x': stat.S_IXOTH},
    'a': {
        'r': (stat.S_IRUSR | stat.S_IRGRP | stat.S_IROTH),
        'w': (stat.S_IWUSR | stat.S_IWGRP | stat.S_IWOTH),
        'x': (stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    }
}


def apply_mode_spec(spec, mode):
    """
    Given a symbolic file mode change specification in the style of chmod(1)
    `spec`, apply changes in the specification to the numeric file mode `mode`.
    """
    for clause in spec.split(','):
        match = CHMOD_CLAUSE_PAT.match(clause)
        who, op, perms = match.groups()
        for ch in who or 'a':
            mask = CHMOD_MASKS[ch]
            bits = CHMOD_BITS[ch]
            cur_perm_bits = mode & mask
            new_perm_bits = reduce(operator.or_, (bits[p] for p in perms), 0)
            mode &= ~mask
            if op == '=':
                mode |= new_perm_bits
            elif op == '+':
                mode |= new_perm_bits | cur_perm_bits
            else:
                mode |= cur_perm_bits & ~new_perm_bits
    return mode


def set_file_mode(path, spec):
    """
    Update the permissions of a file using the same syntax as chmod(1).
    """
    mode = os.stat(path).st_mode

    if spec.isdigit():
        new_mode = int(spec, 8)
    else:
        new_mode = apply_mode_spec(spec, mode)

    os.chmod(path, new_mode)
