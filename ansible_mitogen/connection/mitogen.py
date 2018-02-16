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
import os

import ansible.errors
import ansible.plugins.connection
import ansible_mitogen.helpers
import mitogen.unix

from ansible_mitogen.utils import cast


class Connection(ansible.plugins.connection.ConnectionBase):
    router = None
    context = None

    become_methods = ['sudo']
    transport = 'mitogen'

    @property
    def connected(self):
        return self.router is not None

    def _connect_local(self):
        return mitogen.service.call(self.parent, 500, {
            'method': 'local',
        })

    def _connect_ssh(self):
        return mitogen.service.call(self.parent, 500, cast({
            'method': 'ssh',
            'hostname': self._play_context.remote_addr,
            'username': self._play_context.remote_user,
            'password': self._play_context.password,
            'port': self._play_context.port,
            'python_path': '/usr/bin/python',
            'ssh_path': self._play_context.ssh_executable,
        }))

    def _connect_sudo(self, via):
        return mitogen.service.call(self.parent, 500, cast({
            'method': 'sudo',
            'username': self._play_context.become_user,
            'password': self._play_context.password,
            'python_path': '/usr/bin/python',
            'via': via,
            'debug': True,
        }))

    def _connect(self):
        if self.connected:
            return

        path = os.environ['LISTENER_SOCKET_PATH']
        self.router, self.parent = mitogen.unix.connect(path)

        if self._play_context.connection == 'local':
            host = self._connect_local()
        else:
            host = self._connect_ssh()

        if not self._play_context.become:
            self.context = host
        else:
            self.context = self._connect_sudo(via=host)

    def call_async(self, func, *args, **kwargs):
        self._connect()
        print[func, args, kwargs]
        return self.context.call_async(func, *args, **kwargs)

    def call(self, func, *args, **kwargs):
        return self.call_async(func, *args, **kwargs).get().unpickle()

    def exec_command(self, cmd, in_data=None, sudoable=True):
        super(Connection, self).exec_command(cmd, in_data=in_data, sudoable=sudoable)
        if in_data:
            raise ansible.errors.AnsibleError("does not support module pipelining")
        return self.py_call(ansible_mitogen.helpers.exec_command,
                            cast(cmd), cast(in_data))

    def fetch_file(self, in_path, out_path):
        output = self.py_call(ansible_mitogen.helpers.read_path,
                              cast(in_path))
        ansible_mitogen.helpers.write_path(out_path, output)

    def put_file(self, in_path, out_path):
        self.py_call(ansible_mitogen.helpers.write_path, cast(out_path),
                     ansible_mitogen.helpers.read_path(in_path))

    def close(self):
        self.router.broker.shutdown()
        self.router.broker.join()
