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
Functionality to allow establishing new slave contexts over an SSH connection.
"""

import commands
import logging
import time

import mitogen.parent


LOG = logging.getLogger('mitogen')

PASSWORD_PROMPT = 'password'
PERMDENIED_PROMPT = 'permission denied'


class PasswordError(mitogen.core.Error):
    pass


class Stream(mitogen.parent.Stream):
    create_child = staticmethod(mitogen.parent.tty_create_child)
    python_path = 'python2.7'

    #: The path to the SSH binary.
    ssh_path = 'ssh'

    identity_file = None
    password = None
    port = None
    ssh_args = None

    def construct(self, hostname, username=None, ssh_path=None, port=None,
                  check_host_keys=True, password=None, identity_file=None,
                  compression=True, ssh_args=None, **kwargs):
        super(Stream, self).construct(**kwargs)
        self.hostname = hostname
        self.username = username
        self.port = port
        self.check_host_keys = check_host_keys
        self.password = password
        self.identity_file = identity_file
        self.compression = compression
        if ssh_path:
            self.ssh_path = ssh_path
        if ssh_args:
            self.ssh_args = ssh_args

    def get_boot_command(self):
        bits = [self.ssh_path]
        # bits += ['-o', 'BatchMode yes']

        if self.username:
            bits += ['-l', self.username]
        if self.port is not None:
            bits += ['-p', str(self.port)]
        if self.identity_file or self.password:
            bits += ['-o', 'IdentitiesOnly yes']
        if self.identity_file:
            bits += ['-i', self.identity_file]
        if self.compression:
            bits += ['-o', 'Compression yes']
        if not self.check_host_keys:
            bits += [
                '-o', 'StrictHostKeyChecking no',
                '-o', 'UserKnownHostsFile /dev/null',
            ]
        if self.ssh_args:
            bits += self.ssh_args
        bits.append(self.hostname)
        base = super(Stream, self).get_boot_command()
        return bits + [commands.mkarg(s).strip() for s in base]

    def connect(self):
        super(Stream, self).connect()
        self.name = 'ssh.' + self.hostname
        if self.port:
            self.name += ':%s' % (self.port,)

    auth_incorrect_msg = 'SSH authentication is incorrect'
    password_incorrect_msg = 'SSH password is incorrect'
    password_required_msg = 'SSH password was requested, but none specified'

    def _connect_bootstrap(self):
        password_sent = False
        it = mitogen.parent.iter_read(
            fd=self.receive_side.fd,
            deadline=self.connect_deadline
        )

        for buf in it:
            LOG.debug('%r: received %r', self, buf)
            if buf.endswith('EC0\n'):
                self._ec0_received()
                return
            elif PERMDENIED_PROMPT in buf.lower():
                if self.password is not None and password_sent:
                    raise PasswordError(self.password_incorrect_msg)
                else:
                    raise PasswordError(self.auth_incorrect_msg)
            elif PASSWORD_PROMPT in buf.lower():
                if self.password is None:
                    raise PasswordError(self.password_required_msg)
                LOG.debug('sending password')
                self.transmit_side.write(self.password + '\n')
                password_sent = True
        raise mitogen.core.StreamError('bootstrap failed')
