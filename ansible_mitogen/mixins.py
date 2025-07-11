# Copyright 2019, David Wilson
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

from __future__ import absolute_import, division, print_function
__metaclass__ = type

import json
import logging
import os
import pwd
import random
import traceback

import ansible
import ansible.plugins.action
import ansible.utils.unsafe_proxy
import ansible.vars.clean

from ansible.module_utils.common.text.converters import to_bytes, to_text
from ansible.module_utils.six.moves import shlex_quote

import mitogen.core
import mitogen.select

import ansible_mitogen.connection
import ansible_mitogen.planner
import ansible_mitogen.target
import ansible_mitogen.utils
import ansible_mitogen.utils.unsafe


LOG = logging.getLogger(__name__)


class ActionModuleMixin(ansible.plugins.action.ActionBase):
    """
    The Mitogen-patched PluginLoader dynamically mixes this into every action
    class that Ansible attempts to load. It exists to override all the
    assumptions built into the base action class that should really belong in
    some middle layer, or at least in the connection layer.

    Functionality is defined here for:

    * Capturing the final set of task variables and giving Connection a chance
      to update its idea of the correct execution environment, before any
      attempt is made to call a Connection method. While it's not expected for
      the interpreter to change on a per-task basis, Ansible permits this, and
      so it must be supported.

    * Overriding lots of methods that try to call out to shell for mundane
      reasons, such as copying files around, changing file permissions,
      creating temporary directories and suchlike.

    * Short-circuiting any use of Ansiballz or related code for executing a
      module remotely using shell commands and SSH.

    * Short-circuiting most of the logic in dealing with the fact that Ansible
      always runs become: tasks across at least the SSH user account and the
      destination user account, and handling the security permission issues
      that crop up due to this. Mitogen always runs a task completely within
      the target user account, so it's not a problem for us.
    """
    def __init__(self, task, connection, *args, **kwargs):
        """
        Verify the received connection is really a Mitogen connection. If not,
        transmute this instance back into the original unadorned base class.

        This allows running the Mitogen strategy in mixed-target playbooks,
        where some targets use SSH while others use WinRM or some fancier UNIX
        connection plug-in. That's because when the Mitogen strategy is active,
        ActionModuleMixin is unconditionally mixed into any action module that
        is instantiated, and there is no direct way for the monkey-patch to
        know what kind of connection will be used upfront.
        """
        super(ActionModuleMixin, self).__init__(task, connection, *args, **kwargs)
        if not isinstance(connection, ansible_mitogen.connection.Connection):
            _, self.__class__ = type(self).__bases__

        # required for python interpreter discovery
        connection.templar = self._templar

        self._mitogen_discovering_interpreter = False
        self._mitogen_interpreter_candidate = None
        self._mitogen_rediscovered_interpreter = False

    def run(self, tmp=None, task_vars=None):
        """
        Override run() to notify Connection of task-specific data, so it has a
        chance to know e.g. the Python interpreter in use.
        """
        self._connection.on_action_run(
            task_vars=task_vars,
            delegate_to_hostname=self._task.delegate_to,
            loader_basedir=self._loader.get_basedir(),
        )
        return super(ActionModuleMixin, self).run(tmp, task_vars)

    COMMAND_RESULT = {
        'rc': 0,
        'stdout': '',
        'stdout_lines': [],
        'stderr': ''
    }

    def fake_shell(self, func, stdout=False):
        """
        Execute a function and decorate its return value in the style of
        _low_level_execute_command(). This produces a return value that looks
        like some shell command was run, when really func() was implemented
        entirely in Python.

        If the function raises :py:class:`mitogen.core.CallError`, this will be
        translated into a failed shell command with a non-zero exit status.

        :param func:
            Function invoked as `func()`.
        :returns:
            See :py:attr:`COMMAND_RESULT`.
        """
        dct = self.COMMAND_RESULT.copy()
        try:
            rc = func()
            if stdout:
                dct['stdout'] = repr(rc)
        except mitogen.core.CallError:
            LOG.exception('While emulating a shell command')
            dct['rc'] = 1
            dct['stderr'] = traceback.format_exc()

        return dct

    def _remote_file_exists(self, path):
        """
        Determine if `path` exists by directly invoking os.path.exists() in the
        target user account.
        """
        LOG.debug('_remote_file_exists(%r)', path)
        return self._connection.get_chain().call(
            ansible_mitogen.target.file_exists,
            ansible_mitogen.utils.unsafe.cast(path)
        )

    def _configure_module(self, module_name, module_args, task_vars=None):
        """
        Mitogen does not use the Ansiballz framework. This call should never
        happen when ActionMixin is active, so crash if it does.
        """
        assert False, "_configure_module() should never be called."

    def _is_pipelining_enabled(self, module_style, wrap_async=False):
        """
        Mitogen does not use SSH pipelining. This call should never happen when
        ActionMixin is active, so crash if it does.
        """
        assert False, "_is_pipelining_enabled() should never be called."

    def _generate_tmp_path(self):
        return os.path.join(
            self._connection.get_good_temp_dir(),
            'ansible_mitogen_action_%016x' % (
                random.getrandbits(8*8),
            )
        )

    def _make_tmp_path(self, remote_user=None):
        """
        Create a temporary subdirectory as a child of the temporary directory
        managed by the remote interpreter.
        """
        LOG.debug('_make_tmp_path(remote_user=%r)', remote_user)
        path = self._generate_tmp_path()
        LOG.debug('Temporary directory: %r', path)
        self._connection.get_chain().call_no_reply(os.mkdir, path)
        self._connection._shell.tmpdir = path
        return path

    def _remove_tmp_path(self, tmp_path):
        """
        Replace the base implementation's invocation of rm -rf, replacing it
        with a pipelined call to :func:`ansible_mitogen.target.prune_tree`.
        """
        LOG.debug('_remove_tmp_path(%r)', tmp_path)
        if tmp_path is None and ansible_mitogen.utils.ansible_version[:2] >= (2, 6):
            tmp_path = self._connection._shell.tmpdir  # 06f73ad578d
        if tmp_path is not None:
            self._connection.get_chain().call_no_reply(
                ansible_mitogen.target.prune_tree,
                tmp_path,
            )
        self._connection._shell.tmpdir = None

    def _transfer_data(self, remote_path, data):
        """
        Used by the base _execute_module(), and in <2.4 also by the template
        action module, and probably others.
        """
        if data is None and ansible_mitogen.utils.ansible_version[:2] <= (2, 18):
            data = '{}'
        if isinstance(data, dict):
            try:
                data = json.dumps(data, ensure_ascii=False)
            except UnicodeDecodeError:
                data = json.dumps(data)
        if not isinstance(data, bytes):
            data = to_bytes(data, errors='surrogate_or_strict')

        LOG.debug('_transfer_data(%r, %s ..%d bytes)',
                  remote_path, type(data), len(data))
        self._connection.put_data(remote_path, data)
        return remote_path

    #: Actions listed here cause :func:`_fixup_perms2` to avoid a needless
    #: roundtrip, as they modify file modes separately afterwards. This is due
    #: to the method prototype having a default of `execute=True`.
    FIXUP_PERMS_RED_HERRING = set(['copy'])

    def _fixup_perms2(self, remote_paths, remote_user=None, execute=True):
        """
        Mitogen always executes ActionBase helper methods in the context of the
        target user account, so it is never necessary to modify permissions
        except to ensure the execute bit is set if requested.
        """
        LOG.debug('_fixup_perms2(%r, remote_user=%r, execute=%r)',
                  remote_paths, remote_user, execute)
        if execute and self._task.action not in self.FIXUP_PERMS_RED_HERRING:
            return self._remote_chmod(remote_paths, mode='u+x')
        return self.COMMAND_RESULT.copy()

    def _remote_chmod(self, paths, mode, sudoable=False):
        """
        Issue an asynchronous set_file_mode() call for every path in `paths`,
        then format the resulting return value list with fake_shell().
        """
        LOG.debug('_remote_chmod(%r, mode=%r, sudoable=%r)',
                  paths, mode, sudoable)
        return self.fake_shell(lambda: mitogen.select.Select.all(
            self._connection.get_chain().call_async(
                ansible_mitogen.target.set_file_mode,
                ansible_mitogen.utils.unsafe.cast(path),
                mode,
            )
            for path in paths
        ))

    def _remote_chown(self, paths, user, sudoable=False):
        """
        Issue an asynchronous os.chown() call for every path in `paths`, then
        format the resulting return value list with fake_shell().
        """
        LOG.debug('_remote_chown(%r, user=%r, sudoable=%r)',
                  paths, user, sudoable)
        ent = self._connection.get_chain().call(pwd.getpwnam, user)
        return self.fake_shell(lambda: mitogen.select.Select.all(
            self._connection.get_chain().call_async(
                os.chown, path, ent.pw_uid, ent.pw_gid
            )
            for path in paths
        ))

    def _remote_expand_user(self, path, sudoable=True):
        """
        Replace the base implementation's attempt to emulate
        os.path.expanduser() with an actual call to os.path.expanduser().

        :param bool sudoable:
            If :data:`True`, indicate unqualified tilde ("~" with no username)
            should be evaluated in the context of the login account, not any
            become_user.
        """
        LOG.debug('_remote_expand_user(%r, sudoable=%r)', path, sudoable)
        if not path.startswith('~'):
            # /home/foo -> /home/foo
            return path
        if sudoable or not self._connection.become:
            if path == '~':
                # ~ -> /home/dmw
                return self._connection.homedir
            if path.startswith('~/'):
                # ~/.ansible -> /home/dmw/.ansible
                return os.path.join(self._connection.homedir, path[2:])
        # ~root/.ansible -> /root/.ansible
        return self._connection.get_chain(use_login=(not sudoable)).call(
            os.path.expanduser,
            ansible_mitogen.utils.unsafe.cast(path),
        )

    def get_task_timeout_secs(self):
        """
        Return the task "async:" value, portable across 2.4-2.5.
        """
        try:
            return self._task.async_val
        except AttributeError:
            return getattr(self._task, 'async')

    def _set_temp_file_args(self, module_args, wrap_async):
        # Ansible>2.5 module_utils reuses the action's temporary directory if
        # one exists. Older versions error if this key is present.
        if ansible_mitogen.utils.ansible_version[:2] >= (2, 5):
            if wrap_async:
                # Sharing is not possible with async tasks, as in that case,
                # the directory must outlive the action plug-in.
                module_args['_ansible_tmpdir'] = None
            else:
                module_args['_ansible_tmpdir'] = self._connection._shell.tmpdir

        # If _ansible_tmpdir is unset, Ansible>2.6 module_utils will use
        # _ansible_remote_tmp as the location to create the module's temporary
        # directory. Older versions error if this key is present.
        if ansible_mitogen.utils.ansible_version[:2] >= (2, 6):
            module_args['_ansible_remote_tmp'] = (
                self._connection.get_good_temp_dir()
            )

    def _execute_module(self, module_name=None, module_args=None, tmp=None,
                        task_vars=None, persist_files=False,
                        delete_remote_tmp=True, wrap_async=False,
                        ignore_unknown_opts=False,
                        ):
        """
        Collect up a module's execution environment then use it to invoke
        target.run_module() or helpers.run_module_async() in the target
        context.
        """
        if module_name is None:
            module_name = self._task.action
        if module_args is None:
            module_args = self._task.args
        if task_vars is None:
            task_vars = {}

        if ansible_mitogen.utils.ansible_version[:2] >= (2, 17):
            self._update_module_args(
                module_name, module_args, task_vars,
                ignore_unknown_opts=ignore_unknown_opts,
            )
        else:
            self._update_module_args(module_name, module_args, task_vars)
        env = {}
        self._compute_environment_string(env)
        self._set_temp_file_args(module_args, wrap_async)

        # there's a case where if a task shuts down the node and then immediately calls
        # wait_for_connection, the `ping` test from Ansible won't pass because we lost connection
        # clearing out context forces a reconnect
        # see https://github.com/dw/mitogen/issues/655 and Ansible's `wait_for_connection` module for more info
        if module_name == 'ansible.legacy.ping' and type(self).__name__ == 'wait_for_connection':
            self._connection.context = None

        self._connection._connect()
        result = ansible_mitogen.planner.invoke(
            ansible_mitogen.planner.Invocation(
                action=self,
                connection=self._connection,
                module_name=ansible_mitogen.utils.unsafe.cast(mitogen.core.to_text(module_name)),
                module_args=ansible_mitogen.utils.unsafe.cast(module_args),
                task_vars=task_vars,
                templar=self._templar,
                env=ansible_mitogen.utils.unsafe.cast(env),
                wrap_async=wrap_async,
                timeout_secs=self.get_task_timeout_secs(),
            )
        )

        if tmp and delete_remote_tmp and ansible_mitogen.utils.ansible_version[:2] < (2, 5):
            # Built-in actions expected tmpdir to be cleaned up automatically
            # on _execute_module().
            self._remove_tmp_path(tmp)

        # prevents things like discovered_interpreter_* or ansible_discovered_interpreter_* from being set
        ansible.vars.clean.remove_internal_keys(result)

        # taken from _execute_module of ansible 2.8.6
        # propagate interpreter discovery results back to the controller
        if self._discovered_interpreter_key:
            if result.get('ansible_facts') is None:
                result['ansible_facts'] = {}

            # only cache discovered_interpreter if we're not running a rediscovery
            # rediscovery happens in places like docker connections that could have different
            # python interpreters than the main host
            if not self._mitogen_rediscovered_interpreter:
                result['ansible_facts'][self._discovered_interpreter_key] = self._discovered_interpreter

        discovery_warnings = getattr(self, '_discovery_warnings', [])
        if discovery_warnings:
            if result.get('warnings') is None:
                result['warnings'] = []
            result['warnings'].extend(discovery_warnings)

        discovery_deprecation_warnings = getattr(self, '_discovery_deprecation_warnings', [])
        if discovery_deprecation_warnings:
            if result.get('deprecations') is None:
                result['deprecations'] = []
            result['deprecations'].extend(discovery_deprecation_warnings)

        return ansible.utils.unsafe_proxy.wrap_var(result)

    def _postprocess_response(self, result):
        """
        Apply fixups mimicking ActionBase._execute_module(); this is copied
        verbatim from action/__init__.py, the guts of _parse_returned_data are
        garbage and should be removed or reimplemented once tests exist.

        :param dict result:
            Dictionary with format::

                {
                    "rc": int,
                    "stdout": "stdout data",
                    "stderr": "stderr data"
                }
        """
        if ansible_mitogen.utils.ansible_version[:2] >= (2, 19):
            data = self._parse_returned_data(result, profile='legacy')
        else:
            data = self._parse_returned_data(result)

        # Cutpasted from the base implementation.
        if 'stdout' in data and 'stdout_lines' not in data:
            data['stdout_lines'] = (data['stdout'] or u'').splitlines()
        if 'stderr' in data and 'stderr_lines' not in data:
            data['stderr_lines'] = (data['stderr'] or u'').splitlines()

        return data

    def _low_level_execute_command(self, cmd, sudoable=True, in_data=None,
                                   executable=None,
                                   encoding_errors='surrogate_then_replace',
                                   chdir=None):
        """
        Override the base implementation by simply calling
        target.exec_command() in the target context.
        """
        LOG.debug('_low_level_execute_command(%r, in_data=%r, exe=%r, dir=%r)',
                  cmd, type(in_data), executable, chdir)

        if executable is None:  # executable defaults to False
            executable = self._play_context.executable
        if executable:
            cmd = executable + ' -c ' + shlex_quote(cmd)

        # TODO: HACK: if finding python interpreter then we need to keep
        # calling exec_command until we run into the right python we'll use
        # chicken-and-egg issue, mitogen needs a python to run low_level_execute_command
        # which is required by Ansible's discover_interpreter function
        if self._mitogen_discovering_interpreter:
            possible_pythons = [
                '/usr/bin/python',
                'python3',
                'python3.7',
                'python3.6',
                'python3.5',
                'python2.7',
                'python2.6',
                '/usr/libexec/platform-python',
                '/usr/bin/python3',
                'python'
            ]
        else:
            # not used, just adding a filler value
            possible_pythons = ['python']

        for possible_python in possible_pythons:
            try:
                self._mitogen_interpreter_candidate = possible_python
                rc, stdout, stderr = self._connection.exec_command(
                    cmd, in_data, sudoable, mitogen_chdir=chdir,
                )
            # TODO: what exception is thrown?
            except:
                # we've reached the last python attempted and failed
                if possible_python == possible_pythons[-1]:
                    raise
                else:
                    continue

        stdout_text = to_text(stdout, errors=encoding_errors)
        stderr_text = to_text(stderr, errors=encoding_errors)

        return {
            'rc': rc,
            'stdout': stdout_text,
            'stdout_lines': stdout_text.splitlines(),
            'stderr': stderr_text,
            'stderr_lines': stderr_text.splitlines(),
        }
