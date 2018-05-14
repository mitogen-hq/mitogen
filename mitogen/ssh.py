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

import logging
import time

try:
    from shlex import quote as shlex_quote
except ImportError:
    from pipes import quote as shlex_quote

import mitogen.parent


LOG = logging.getLogger('mitogen')

PASSWORD_PROMPT = 'password:'
PERMDENIED_PROMPT = 'permission denied'
HOSTKEY_REQ_PROMPT = 'are you sure you want to continue connecting (yes/no)?'
HOSTKEY_FAIL = 'host key verification failed.'


class PasswordError(mitogen.core.StreamError):
    pass


class HostKeyError(mitogen.core.StreamError):
    pass


class Stream(mitogen.parent.Stream):
    create_child = staticmethod(mitogen.parent.hybrid_tty_create_child)
    child_is_immediate_subprocess = False
    python_path = 'python2.7'

    #: Once connected, points to the corresponding TtyLogStream, allowing it to
    #: be disconnected at the same time this stream is being torn down.
    tty_stream = None

    #: The path to the SSH binary.
    ssh_path = 'ssh'

    hostname = None
    username = None
    port = None

    identity_file = None
    password = None
    ssh_args = None

    check_host_keys_msg = 'check_host_keys= must be set to accept, enforce or ignore'

    def construct(self, hostname, username=None, ssh_path=None, port=None,
                  check_host_keys='enforce', password=None, identity_file=None,
                  compression=True, ssh_args=None, keepalive_enabled=True,
                  keepalive_count=3, keepalive_interval=15, **kwargs):
        super(Stream, self).construct(**kwargs)
        if check_host_keys not in ('accept', 'enforce', 'ignore'):
            raise ValueError(self.check_host_keys_msg)

        self.hostname = hostname
        self.username = username
        self.port = port
        self.check_host_keys = check_host_keys
        self.password = password
        self.identity_file = identity_file
        self.compression = compression
        self.keepalive_enabled = keepalive_enabled
        self.keepalive_count = keepalive_count
        self.keepalive_interval = keepalive_interval
        if ssh_path:
            self.ssh_path = ssh_path
        if ssh_args:
            self.ssh_args = ssh_args

    def on_disconnect(self, broker):
        self.tty_stream.on_disconnect(broker)
        super(Stream, self).on_disconnect(broker)

    def get_boot_command(self):
        bits = [self.ssh_path]
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
        if self.keepalive_enabled:
            bits += [
                '-o', 'ServerAliveInterval %s' % (self.keepalive_interval,),
                '-o', 'ServerAliveCountMax %s' % (self.keepalive_count,),
            ]
        if self.check_host_keys == 'enforce':
            bits += ['-o', 'StrictHostKeyChecking yes']
        if self.check_host_keys == 'accept':
            bits += ['-o', 'StrictHostKeyChecking ask']
        elif self.check_host_keys == 'ignore':
            bits += [
                '-o', 'StrictHostKeyChecking no',
                '-o', 'UserKnownHostsFile /dev/null',
                '-o', 'GlobalKnownHostsFile /dev/null',
            ]
        if self.ssh_args:
            bits += self.ssh_args
        bits.append(self.hostname)
        base = super(Stream, self).get_boot_command()
        return bits + [shlex_quote(s).strip() for s in base]

    def connect(self):
        super(Stream, self).connect()
        self.name = 'ssh.' + self.hostname
        if self.port:
            self.name += ':%s' % (self.port,)

    auth_incorrect_msg = 'SSH authentication is incorrect'
    password_incorrect_msg = 'SSH password is incorrect'
    password_required_msg = 'SSH password was requested, but none specified'
    hostkey_config_msg = (
        'SSH requested permission to accept unknown host key, but '
        'check_host_keys=ignore. This is likely due to ssh_args=  '
        'conflicting with check_host_keys=. Please correct your '
        'configuration.'
    )
    hostkey_failed_msg = (
        'Host key checking is enabled, and SSH reported an unrecognized or '
        'mismatching host key.'
    )

    def _host_key_prompt(self):
        if self.check_host_keys == 'accept':
            LOG.debug('%r: accepting host key', self)
            self.tty_stream.transmit_side.write('y\n')
            return

        # _host_key_prompt() should never be reached with ignore or enforce
        # mode, SSH should have handled that. User's ssh_args= is conflicting
        # with ours.
        raise HostKeyError(self.hostkey_config_msg)

    def _connect_bootstrap(self, extra_fd):
        self.tty_stream = mitogen.parent.TtyLogStream(extra_fd, self)

        password_sent = False
        it = mitogen.parent.iter_read(
            fds=[self.receive_side.fd, extra_fd],
            deadline=self.connect_deadline
        )

        for buf in it:
            LOG.debug('%r: received %r', self, buf)
            if buf.endswith('EC0\n'):
                self._ec0_received()
                return
            elif HOSTKEY_REQ_PROMPT in buf.lower():
                self._host_key_prompt()
            elif HOSTKEY_FAIL in buf.lower():
                raise HostKeyError(self.hostkey_failed_msg)
            elif PERMDENIED_PROMPT in buf.lower():
                if self.password is not None and password_sent:
                    raise PasswordError(self.password_incorrect_msg)
                else:
                    raise PasswordError(self.auth_incorrect_msg)
            elif PASSWORD_PROMPT in buf.lower():
                if self.password is None:
                    raise PasswordError(self.password_required_msg)
                LOG.debug('%r: sending password', self)
                self.tty_stream.transmit_side.write(self.password + '\n')
                password_sent = True

        raise mitogen.core.StreamError('bootstrap failed')
