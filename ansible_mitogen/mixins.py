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

from __future__ import absolute_import
import commands
import os
import pwd
import shutil
import tempfile

import ansible
import ansible.plugins
import ansible.plugins.action

try:
    from ansible.plugins.loader import module_loader
except ImportError:  # Ansible<2.4
    from ansible.plugins import module_loader

import mitogen.core
import mitogen.master
from mitogen.utils import cast

import ansible_mitogen.helpers
from ansible.module_utils._text import to_text


def get_command_module_name(module_name):
    """
    Given the name of an Ansible command module, return its canonical module
    path within the ansible.

    :param module_name:
        "shell"
    :return:
        "ansible.modules.commands.shell"
    """
    path = module_loader.find_plugin(module_name, '')
    relpath = os.path.relpath(path, os.path.dirname(ansible.__file__))
    root, _ = os.path.splitext(relpath)
    return 'ansible.' + root.replace('/', '.')


class ActionModuleMixin(ansible.plugins.action.ActionBase):
    def call(self, func, *args, **kwargs):
        return self._connection.call(func, *args, **kwargs)

    COMMAND_RESULT = {
        'rc': 0,
        'stdout': '',
        'stdout_lines': [],
        'stderr': ''
    }

    def fake_shell(self, func, stdout=False):
        dct = self.COMMAND_RESULT.copy()
        try:
            rc = func()
            if stdout:
                dct['stdout'] = repr(rc)
        except mitogen.core.CallError:
            dct['rc'] = 1
            dct['stderr'] = traceback.format_exc()

        return dct

    def _remote_file_exists(self, path):
        # replaces 5 lines.
        return self.call(os.path.exists, path)

    def _configure_module(self, module_name, module_args, task_vars=None):
        # replaces 58 lines
        assert False, "_configure_module() should never be called."

    def _is_pipelining_enabled(self, module_style, wrap_async=False):
        # replaces 17 lines
        return False

    def _make_tmp_path(self, remote_user=None):
        # replaces 58 lines
        path = self.call(tempfile.mkdtemp, prefix='ansible-mitogen-tmp-')
        self._cleanup_remote_tmp = True
        return path

    def _remove_tmp_path(self, tmp_path):
        # replaces 10 lines
        if self._should_remove_tmp_path(tmp_path):
            return self.call(shutil.rmtree, tmp_path)

    def _transfer_data(self, remote_path, data):
        # replaces 20 lines
        assert False, "_transfer_data() should never be called."

    def _fixup_perms2(self, remote_paths, remote_user=None, execute=True):
        # replaces 83 lines
        assert False, "_fixup_perms2() should never be called."

    def _remote_chmod(self, paths, mode, sudoable=False):
        return self.fake_shell(lambda: mitogen.master.Select.all(
            self._connection.call_async(os.chmod, path, mode)
            for path in paths
        ))

    def _remote_chown(self, paths, user, sudoable=False):
        ent = self.call(pwd.getpwnam, user)
        return self.fake_shell(lambda: mitogen.master.Select.all(
            self._connection.call_async(os.chown, path, ent.pw_uid, ent.pw_gid)
            for path in paths
        ))

    def _remote_expand_user(self, path, sudoable=True):
        # replaces 25 lines
        if path.startswith('~'):
            path = self.call(os.path.expanduser, path)
        return path

    def _execute_module(self, module_name=None, module_args=None, tmp=None,
                        task_vars=None, persist_files=False,
                        delete_remote_tmp=True, wrap_async=False):
        module_name = module_name or self._task.action
        module_args = module_args or self._task.args
        task_vars = task_vars or {}

        self._update_module_args(module_name, module_args, task_vars)

        # replaces 110 lines
        js = self.call(
            ansible_mitogen.helpers.run_module,
            get_command_module_name(module_name),
            args=cast(module_args)
        )

        data = self._parse_returned_data({
            'rc': 0,
            'stdout': js,
            'stdout_lines': [js],
            'stderr': ''
        })

        if wrap_async:
            data['changed'] = True

        # pre-split stdout/stderr into lines if needed
        if 'stdout' in data and 'stdout_lines' not in data:
            # if the value is 'False', a default won't catch it.
            txt = data.get('stdout', None) or u''
            data['stdout_lines'] = txt.splitlines()
        if 'stderr' in data and 'stderr_lines' not in data:
            # if the value is 'False', a default won't catch it.
            txt = data.get('stderr', None) or u''
            data['stderr_lines'] = txt.splitlines()

        return data

    def _low_level_execute_command(self, cmd, sudoable=True, in_data=None,
                                   executable=None,
                                   encoding_errors='surrogate_then_replace',
                                   chdir=None):
        if executable is None:  # executable defaults to False
            executable = self._play_context.executable
        if executable:
            cmd = executable + ' -c ' + commands.mkarg(cmd)

        # replaces 57 lines
        # replaces 126 lines of make_become_cmd()
        rc, stdout, stderr = self.call(
            ansible_mitogen.helpers.exec_command,
            cast(cmd),
            cast(in_data),
            chdir=cast(chdir),
        )
        return {
            'rc': rc,
            'stdout': to_text(stdout, errors=encoding_errors),
            'stdout_lines': to_text(stdout, errors=encoding_errors).splitlines(),
            'stderr': stderr,
        }
