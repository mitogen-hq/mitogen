"""
Functionality to allow establishing new slave contexts over an SSH connection.
"""

import commands

import mitogen.master


class Stream(mitogen.master.Stream):
    python_path = 'python'

    #: The path to the SSH binary.
    ssh_path = 'ssh'

    port = None

    def construct(self, hostname, username=None, ssh_path=None, port=None,
                  check_host_keys=True, **kwargs):
        super(Stream, self).construct(**kwargs)
        self.hostname = hostname
        self.username = username
        self.port = port
        self.check_host_keys = check_host_keys
        if ssh_path:
            self.ssh_path = ssh_path

    def get_boot_command(self):
        bits = [self.ssh_path]
        bits += ['-o', 'BatchMode yes']

        if self.username:
            bits += ['-l', self.username]
        if self.port is not None:
            bits += ['-p', str(self.port)]
        if not self.check_host_keys:
            bits += [
                '-o', 'StrictHostKeyChecking no',
                '-o', 'UserKnownHostsFile /dev/null',
            ]
        bits.append(self.hostname)
        base = super(Stream, self).get_boot_command()
        return bits + map(commands.mkarg, base)

    def connect(self):
        super(Stream, self).connect()
        self.name = 'ssh.' + self.hostname
        if self.port:
            self.name += ':%s' % (self.port,)
