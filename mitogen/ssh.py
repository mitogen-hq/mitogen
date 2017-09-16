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
                 **kwargs):
        super(Stream, self).construct(**kwargs)
        self.hostname = hostname
        self.username = username
        self.port = port
        if ssh_path:
            self.ssh_path = ssh_path

    def get_boot_command(self):
        bits = [self.ssh_path]
        if self.username:
            bits += ['-l', self.username]
        if self.port is not None:
            bits += ['-p', str(self.port)]
        bits.append(self.hostname)
        base = super(Stream, self).get_boot_command()
        return bits + map(commands.mkarg, base)

    def connect(self):
        super(Stream, self).connect()
        self.name = 'ssh.' + self.hostname
        if self.port:
            self.name += ':%s' % (self.port,)
