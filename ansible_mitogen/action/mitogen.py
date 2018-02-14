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
import os

import ansible
import ansible.plugins
import ansible.plugins.action.normal
import ansible_mitogen.helpers


ANSIBLE_BASEDIR = os.path.dirname(ansible.__file__)


class ActionModule(ansible.plugins.action.normal.ActionModule):
    def get_py_module_name(self, module_name):
        path = ansible.plugins.module_loader.find_plugin(module_name, '')
        relpath = os.path.relpath(path, ANSIBLE_BASEDIR)
        root, _ = os.path.splitext(relpath)
        return 'ansible.' + root.replace('/', '.')

    def _execute_module(self, module_name=None, module_args=None, tmp=None,
                        task_vars=None, persist_files=False,
                        delete_remote_tmp=True, wrap_async=False):

        module_name = module_name or self._task.action
        module_args = module_args or self._task.args
        task_vars = task_vars or {}

        self._update_module_args(module_name, module_args, task_vars)

        #####################################################################

        py_module_name = self.get_py_module_name(module_name)
        js = self._connection.py_call(ansible_mitogen.helpers.run_module, py_module_name,
                                      args=json.loads(json.dumps(module_args)))

        #####################################################################

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
