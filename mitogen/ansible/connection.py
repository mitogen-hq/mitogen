"""
Basic Ansible connection plug-in mostly useful for testing functionality,
due to Ansible's use of the multiprocessing package a lot more work is required
to share the mitogen SSH connection across tasks.

Enable it by:

    $ cat ansible.cfg
    [defaults]
    connection_plugins = plugins/connection

    $ mkdir -p plugins/connection
    $ cat > plugins/connection/mitogen_conn.py <<-EOF
    from mitogen.ansible.connection import Connection
    EOF
"""

import mitogen.master
import mitogen.ssh
import mitogen.utils
from mitogen.ansible import helpers

import ansible.errors
import ansible.plugins.connection


class Connection(ansible.plugins.connection.ConnectionBase):
    broker = None
    context = None

    become_methods = []
    transport = 'mitogen'

    @property
    def connected(self):
        return self.broker is not None

    def _connect(self):
        if self.connected:
            return
        self.broker = mitogen.master.Broker()
        if self._play_context.remote_addr == 'localhost':
            self.context = mitogen.master.connect(self.broker)
        else:
            self.context = mitogen.ssh.connect(broker,
                self._play_context.remote_addr)

    def exec_command(self, cmd, in_data=None, sudoable=True):
        super(Connection, self).exec_command(cmd, in_data=in_data, sudoable=sudoable)
        if in_data:
            raise ansible.errors.AnsibleError("does not support module pipelining")

        return self.context.call(helpers.exec_command, cmd, in_data)

    def fetch_file(self, in_path, out_path):
        output = self.context.call(helpers.read_path, in_path)
        helpers.write_path(out_path, output)

    def put_file(self, in_path, out_path):
        self.context.call(helpers.write_path, out_path,
                          helpers.read_path(in_path))

    def close(self):
        self.broker.shutdown()
        self.broker.join()
