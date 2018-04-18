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

"""
Helper functions intended to be executed on the target. These are entrypoints
for file transfer, module execution and sundry bits like changing file modes.
"""

from __future__ import absolute_import
import json
import logging
import operator
import os
import pwd
import random
import re
import stat
import subprocess
import tempfile
import threading
import zlib

import ansible_mitogen.runner
import ansible_mitogen.services
import mitogen.core
import mitogen.fork
import mitogen.parent
import mitogen.service


LOG = logging.getLogger(__name__)

#: Caching of fetched file data.
_file_cache = {}

#: Initialized to an econtext.parent.Context pointing at a pristine fork of
#: the target Python interpreter before it executes any code or imports.
_fork_parent = None


def get_file(context, path):
    """
    Basic in-memory caching module fetcher. This generates an one roundtrip for
    every previously unseen file, so it is only a temporary solution.

    :param context:
        Context we should direct FileService requests to. For now (and probably
        forever) this is just the top-level Mitogen connection manager process.
    :param path:
        Path to fetch from FileService, must previously have been registered by
        a privileged context using the `register` command.
    :returns:
        Bytestring file data.
    """
    if path not in _file_cache:
        LOG.debug('target.get_file(): fetching %r from %r', path, context)
        _file_cache[path] = zlib.decompress(
            mitogen.service.call(
                context=context,
                handle=ansible_mitogen.services.FileService.handle,
                method='fetch',
                kwargs={
                    'path': path
                }
            )
        )
        LOG.debug('target.get_file(): fetched %r from %r', path, context)

    return _file_cache[path]


@mitogen.core.takes_econtext
def start_fork_parent(econtext):
    """
    Called by ContextService immediately after connection; arranges for the
    (presently) spotless Python interpreter to be forked, where the newly
    forked interpreter becomes the parent of any newly forked future
    interpreters.

    This is necessary to prevent modules that are executed in-process from
    polluting the global interpreter state in a way that effects explicitly
    isolated modules.
    """
    global _fork_parent
    mitogen.parent.upgrade_router(econtext)
    _fork_parent = econtext.router.fork()


@mitogen.core.takes_econtext
def start_fork_child(kwargs, econtext):
    mitogen.parent.upgrade_router(econtext)
    context = econtext.router.fork()
    kwargs['shutdown_on_exit'] = True
    context.call_async(run_module, kwargs)


@mitogen.core.takes_econtext
def run_module(kwargs, econtext):
    """
    Set up the process environment in preparation for running an Ansible
    module. This monkey-patches the Ansible libraries in various places to
    prevent it from trying to kill the process on completion, and to prevent it
    from reading sys.stdin.
    """
    should_fork = kwargs.pop('should_fork', False)
    shutdown_on_exit = kwargs.pop('shutdown_on_exit', False)
    if should_fork:
        _fork_parent.call(start_fork_child, kwargs)
        return

    runner_name = kwargs.pop('runner_name')
    klass = getattr(ansible_mitogen.runner, runner_name)
    impl = klass(**kwargs)
    impl.run()
    if shutdown_on_exit:
        econtext.broker.shutdown()


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


def exec_args(args, in_data='', chdir=None, shell=None, emulate_tty=False):
    """
    Run a command in a subprocess, emulating the argument handling behaviour of
    SSH.

    :param list[str]:
        Argument vector.
    :param bytes in_data:
        Optional standard input for the command.
    :param bool emulate_tty:
        If :data:`True`, arrange for stdout and stderr to be merged into the
        stdout pipe and for LF to be translated into CRLF, emulating the
        behaviour of a TTY.
    :return:
        (return code, stdout bytes, stderr bytes)
    """
    LOG.debug('exec_args(%r, ..., chdir=%r)', args, chdir)
    assert isinstance(args, list)

    if emulate_tty:
        stderr = subprocess.STDOUT
    else:
        stderr = subprocess.PIPE

    proc = subprocess.Popen(
        args=args,
        stdout=subprocess.PIPE,
        stderr=stderr,
        stdin=subprocess.PIPE,
        cwd=chdir,
    )
    stdout, stderr = proc.communicate(in_data)

    if emulate_tty:
        stdout = stdout.replace('\n', '\r\n')
    return proc.returncode, stdout, stderr or ''


def exec_command(cmd, in_data='', chdir=None, shell=None, emulate_tty=False):
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
    return exec_args(
        args=[get_user_shell(), '-c', cmd],
        in_data=in_data,
        chdir=chdir,
        shell=shell,
        emulate_tty=emulate_tty,
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
