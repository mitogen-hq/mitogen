"""
Basic Ansible connection plug-in mostly useful for testing functionality,
due to Ansible's use of the multiprocessing package a lot more work is required
to share the econtext SSH connection across tasks.

Enable it by:

    $ cat ansible.cfg
    [defaults]
    connection_plugins = plugins/connection

    $ mkdir -p plugins/connection
    $ cat > plugins/connection/econtext_conn.py <<-EOF
    from econtext.ansible.connection import Connection
    EOF
"""

import econtext.master
import econtext.utils
from econtext.ansible import helpers

import ansible.plugins.connection


class Connection(ansible.plugins.connection.ConnectionBase):
    broker = None
    context = None

    become_methods = []
    transport = 'econtext'

    @property
    def connected(self):
        return self.broker is not None

    def _connect(self):
        if self.connected:
            return
        self.broker = econtext.master.Broker()
        if self._play_context.remote_addr == 'localhost':
            self.context = self.broker.get_local()
        else:
            self.context = self.broker.get_remote(self._play_context.remote_addr)

    def exec_command(self, cmd, in_data=None, sudoable=True):
        super(Connection, self).exec_command(cmd, in_data=in_data, sudoable=sudoable)
        if in_data:
            raise AnsibleError("does not support module pipelining")

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
