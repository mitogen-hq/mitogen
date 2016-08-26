"""
Functionality to allow establishing new slave contexts over an SSH connection.
"""

import commands

import econtext.master


class Stream(econtext.master.Stream):
    python_path = 'python'
    #: The path to the SSH binary.
    ssh_path = 'ssh'

    def get_boot_command(self):
        bits = [self.ssh_path]
        if self._context.username:
            bits += ['-l', self._context.username]
        bits.append(self._context.hostname)
        base = super(Stream, self).get_boot_command()
        return bits + map(commands.mkarg, base)


def connect(broker, hostname, username=None, name=None,
            ssh_path=None, python_path=None):
    """Get the named remote context, creating it if it does not exist."""
    if name is None:
        name = hostname

    context = econtext.master.Context(broker, name, hostname, username)
    context.stream = Stream(context)
    if python_path:
        context.stream.python_path = python_path
    if ssh_path:
        context.stream.ssh_path = ssh_path
    context.stream.connect()
    return broker.register(context)
