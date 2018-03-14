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
import logging
import os
import shlex
import sys
import time

import ansible.errors
import ansible.plugins.connection

import mitogen.unix
from mitogen.utils import cast

import ansible_mitogen.helpers
from ansible_mitogen.services import ContextService


LOG = logging.getLogger(__name__)


class Connection(ansible.plugins.connection.ConnectionBase):
    #: mitogen.master.Router for this worker.
    router = None

    #: mitogen.master.Context representing the parent Context, which is
    #: presently always the master process.
    parent = None

    #: mitogen.master.Context used to communicate with the target user account.
    context = None

    #: Only sudo is supported for now.
    become_methods = ['sudo']

    #: Set by the constructor according to whichever connection type this
    #: connection should emulate. We emulate the original connection type to
    #: work around artificial limitations in e.g. the synchronize action, which
    #: hard-codes 'local' and 'ssh' as the only allowable connection types.
    transport = None

    #: Set to 'ansible_python_interpreter' by on_action_run().
    python_path = None

    #: Set to 'ansible_sudo_exe' by on_action_run().
    sudo_path = None

    #: Set to 'ansible_ssh_timeout' by on_action_run().
    ansible_ssh_timeout = None

    def __init__(self, play_context, new_stdin, original_transport):
        assert 'MITOGEN_LISTENER_PATH' in os.environ, (
            'The "mitogen" connection plug-in may only be instantiated '
             'by the "mitogen" strategy plug-in.'
        )

        self.original_transport = original_transport
        self.transport = original_transport
        super(Connection, self).__init__(play_context, new_stdin)

    def on_action_run(self, task_vars):
        """
        Invoked by ActionModuleMixin to indicate a new task is about to start
        executing. We use the opportunity to grab relevant bits from the
        task-specific data.
        """
        self.ansible_ssh_timeout = task_vars.get(
            'ansible_ssh_timeout',
            None
        )
        self.python_path = task_vars.get(
            'ansible_python_interpreter',
            '/usr/bin/python'
        )
        self.sudo_path = task_vars.get(
            'ansible_sudo_exe',
            'sudo'
        )

    @property
    def connected(self):
        return self.router is not None

    def _connect_local(self):
        """
        Fetch a reference to the local() Context from ContextService in the
        master process.
        """
        return mitogen.service.call(self.parent, ContextService.handle, cast({
            'method': 'local',
        }))

    def _connect_ssh(self):
        """
        Fetch a reference to an SSH Context matching the play context from
        ContextService in the master process.
        """
        return mitogen.service.call(
            self.parent,
            ContextService.handle,
            cast({
                'method': 'ssh',
                'check_host_keys': False,  # TODO
                'hostname': self._play_context.remote_addr,
                'username': self._play_context.remote_user,
                'password': self._play_context.password,
                'port': self._play_context.port,
                'python_path': self.python_path,
                'identity_file': self._play_context.private_key_file,
                'ssh_path': self._play_context.ssh_executable,
                'connect_timeout': self.ansible_ssh_timeout,
                'ssh_args': [
                    term
                    for s in (
                        getattr(self._play_context, 'ssh_args', ''),
                        getattr(self._play_context, 'ssh_common_args', ''),
                        getattr(self._play_context, 'ssh_extra_args', '')
                    )
                    for term in shlex.split(s or '')
                ]
            })
        )

    def _connect_sudo(self, via=None, python_path=None):
        """
        Fetch a reference to a sudo Context matching the play context from
        ContextService in the master process.

        :param via:
            Parent Context of the sudo Context. For Ansible, this should always
            be a Context returned by _connect_ssh().
        """
        return mitogen.service.call(
            self.parent,
            ContextService.handle,
            cast({
                'method': 'sudo',
                'username': self._play_context.become_user,
                'password': self._play_context.password,
                'python_path': python_path or self.python_path,
                'sudo_path': self.sudo_path,
                'connect_timeout': self._play_context.timeout,
                'via': via,
                'sudo_args': shlex.split(
                    self._play_context.sudo_flags or
                    self._play_context.become_flags or ''
                ),
            })
        )

    def _connect(self):
        """
        Establish a connection to the master process's UNIX listener socket,
        constructing a mitogen.master.Router to communicate with the master,
        and a mitogen.master.Context to represent it.

        Depending on the original transport we should emulate, trigger one of
        the _connect_*() service calls defined above to cause the master
        process to establish the real connection on our behalf, or return a
        reference to the existing one.
        """
        if self.connected:
            return

        path = os.environ['MITOGEN_LISTENER_PATH']
        self.router, self.parent = mitogen.unix.connect(path)

        if self.original_transport == 'local':
            if not self._play_context.become:
                self.context = self._connect_local()
            else:
                self.context = self._connect_sudo(python_path=sys.executable)
        else:
            self.host = self._connect_ssh()
            if not self._play_context.become:
                self.context = self.host
            else:
                self.context = self._connect_sudo(via=self.host)

    def close(self):
        """
        Arrange for the mitogen.master.Router running in the worker to
        gracefully shut down, and wait for shutdown to complete. Safe to call
        multiple times.
        """
        if self.router:
            self.router.broker.shutdown()
            self.router.broker.join()
            self.router = None

    def call_async(self, func, *args, **kwargs):
        """
        Start a function call to the target.

        :returns:
            mitogen.core.Receiver that receives the function call result.
        """
        self._connect()
        return self.context.call_async(func, *args, **kwargs)

    def call(self, func, *args, **kwargs):
        """
        Start and wait for completion of a function call in the target.

        :raises mitogen.core.CallError:
            The function call failed.
        :returns:
            Function return value.
        """
        t0 = time.time()
        try:
            return self.call_async(func, *args, **kwargs).get().unpickle()
        finally:
            LOG.debug('Call %s%r took %d ms', func.func_name, args,
                      1000 * (time.time() - t0))

    def exec_command(self, cmd, in_data='', sudoable=True):
        """
        Implement exec_command() by calling the corresponding
        ansible_mitogen.helpers function in the target.

        :param str cmd:
            Shell command to execute.
        :param bytes in_data:
            Data to supply on ``stdin`` of the process.
        :returns:
            (return code, stdout bytes, stderr bytes)
        """
        return self.call(ansible_mitogen.helpers.exec_command,
                         cast(cmd), cast(in_data))

    def fetch_file(self, in_path, out_path):
        """
        Implement fetch_file() by calling the corresponding
        ansible_mitogen.helpers function in the target.

        :param str in_path:
            Remote filesystem path to read.
        :param str out_path:
            Local filesystem path to write.
        """
        output = self.call(ansible_mitogen.helpers.read_path,
                           cast(in_path))
        ansible_mitogen.helpers.write_path(out_path, output)

    def put_data(self, out_path, data):
        """
        Implement put_file() by caling the corresponding
        ansible_mitogen.helpers function in the target.

        :param str in_path:
            Local filesystem path to read.
        :param str out_path:
            Remote filesystem path to write.
        """
        self.call(ansible_mitogen.helpers.write_path,
                  cast(out_path), cast(data))

    def put_file(self, in_path, out_path):
        """
        Implement put_file() by caling the corresponding
        ansible_mitogen.helpers function in the target.

        :param str in_path:
            Local filesystem path to read.
        :param str out_path:
            Remote filesystem path to write.
        """
        self.put_data(out_path, ansible_mitogen.helpers.read_path(in_path))
