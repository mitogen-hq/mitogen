
"""
Mitogen extends Ansible's regular host configuration mechanism in several ways
that require quite a lot of care:

* Some per-task configurables in Ansible like ansible_python_interpreter are
  connection-layer configurables in Mitogen. They must be extracted during each
  task execution to form the complete connection-layer configuration.

* Mitogen has extra configurables not supported by Ansible at all, such as
  mitogen_ssh_debug_level. These are extracted the same way as
  ansible_python_interpreter.

* Mitogen allows connections to be delegated to other machines. Ansible has no
  internal framework for this, and so Mitogen must figure out a delegated
  connection configuration all for itself. This means it cannot reuse much of
  the Ansible machinery for building a connection configuration, as that
  machinery is deeply spread and out hard-wired to expect Ansible's usual mode
  of operation.

For delegated connections, Ansible's PlayContext information is reused where
possible, but for proxy hops, configurations are built up using the HostVars
magic class to call VariableManager.get_vars() behind the scenes on our behalf.
Where Ansible has multiple sources of a configuration item, for example,
ansible_ssh_extra_args, Mitogen must (ideally perfectly) reproduce how Ansible
arrives at its value, without using mechanisms that are hard-wired or change
across Ansible versions.

That is what this file is for. It exports two spec classes, one that takes all
information from PlayContext, and another that takes (almost) all information
from HostVars.
"""

import os
import ansible.utils.shlex
import ansible.constants as C

import mitogen.core


def parse_python_path(s):
    """
    Given the string set for ansible_python_interpeter, parse it using shell
    syntax and return an appropriate argument vector.
    """
    if s:
        return ansible.utils.shlex.shlex_split(s)


class PlayContextSpec:
    """
    Return a dict representing all important connection configuration, allowing
    the same functions to work regardless of whether configuration came from
    play_context (direct connection) or host vars (mitogen_via=).
    """
    def __init__(self, connection, play_context, transport, inventory_name):
        self._connection = connection
        self._play_context = play_context
        self._transport = transport
        self._inventory_name = inventory_name

    def transport(self):
        return self._transport

    def inventory_name(self):
        return self._inventory_name

    def remote_addr(self):
        return self._play_context.remote_addr

    def remote_user(self):
        return self._play_context.remote_user

    def become(self):
        return self._play_context.become

    def become_method(self):
        return self._play_context.become_method

    def become_user(self):
        return self._play_context.become_user

    def become_pass(self):
        return self._play_context.become_pass

    def password(self):
        return self._play_context.password

    def port(self):
        return self._play_context.port

    def python_path(self):
        return parse_python_path(
            self._connection.get_task_var('ansible_python_interpreter')
        )

    def private_key_file(self):
        return self._play_context.private_key_file

    def ssh_executable(self):
        return self._play_context.ssh_executable

    def timeout(self):
        return self._play_context.timeout

    def ansible_ssh_timeout(self):
        return (
            self._connection.get_task_var('ansible_timeout') or
            self._connection.get_task_var('ansible_ssh_timeout') or
            self._play_context.timeout
        )

    def ssh_args(self):
        return [
            mitogen.core.to_text(term)
            for s in (
                getattr(self._play_context, 'ssh_args', ''),
                getattr(self._play_context, 'ssh_common_args', ''),
                getattr(self._play_context, 'ssh_extra_args', '')
            )
            for term in ansible.utils.shlex.shlex_split(s or '')
        ]

    def become_exe(self):
        return self._play_context.become_exe

    def sudo_args(self):
        return [
            mitogen.core.to_text(term)
            for s in (
                self._play_context.sudo_flags,
                self._play_context.become_flags
            )
            for term in ansible.utils.shlex.shlex_split(s or '')
        ]

    def mitogen_via(self):
        return self._connection.get_task_var('mitogen_via')

    def mitogen_kind(self):
        return self._connection.get_task_var('mitogen_kind')

    def mitogen_docker_path(self):
        return self._connection.get_task_var('mitogen_docker_path')

    def mitogen_kubectl_path(self):
        return self._connection.get_task_var('mitogen_kubectl_path')

    def mitogen_lxc_path(self):
        return self._connection.get_task_var('mitogen_lxc_path')

    def mitogen_lxc_attach_path(self):
        return self._connection.get_task_var('mitogen_lxc_attach_path')

    def mitogen_lxc_info_path(self):
        return self._connection.get_task_var('mitogen_lxc_info_path')

    def mitogen_machinectl_path(self):
        return self._connection.get_task_var('mitogen_machinectl_path')

    def mitogen_ssh_debug_level(self):
        return self._connection.get_task_var('mitogen_ssh_debug_level')

    def extra_args(self):
        return self._connection.get_extra_args()


class MitogenViaSpec:
    def __init__(self, inventory_name, host_vars,
                 become_method, become_user):
        self._inventory_name = inventory_name
        self._host_vars = host_vars
        self._become_method = become_method
        self._become_user = become_user

    def transport(self):
        return (
            self._host_vars.get('ansible_connection') or
            C.DEFAULT_TRANSPORT
        )

    def inventory_name(self):
        return self._inventory_name

    def remote_addr(self):
        return (
            self._host_vars.get('ansible_host') or
            self._inventory_name
        )

    def remote_user(self):
        return (
            self._host_vars.get('ansible_user') or
            self._host_vars.get('ansible_ssh_user') or
            C.DEFAULT_REMOTE_USER
        )

    def become(self):
        return bool(self._become_user)

    def become_method(self):
        return self._become_method or C.DEFAULT_BECOME_METHOD

    def become_user(self):
        return self._become_user

    def become_pass(self):
        return (
            # TODO: Might have to come from PlayContext.
            self._host_vars.get('ansible_become_password') or
            self._host_vars.get('ansible_become_pass')
        )

    def password(self):
        return (
            # TODO: Might have to come from PlayContext.
            self._host_vars.get('ansible_ssh_pass') or
            self._host_vars.get('ansible_password')
        )

    def port(self):
        return (
            self._host_vars.get('ansible_port') or
            C.DEFAULT_REMOTE_PORT
        )

    def python_path(self):
        s = parse_python_path(
            self._host_vars.get('ansible_python_interpreter')
            # This variable has no default for remote hosts. For local hosts it
            # is sys.executable.
        )
        print('hi ho', self.inventory_name(), s)
        return s

    def private_key_file(self):
        # TODO: must come from PlayContext too.
        return (
            self._host_vars.get('ansible_ssh_private_key_file') or
            self._host_vars.get('ansible_private_key_file') or
            C.DEFAULT_PRIVATE_KEY_FILE
        )

    def ssh_executable(self):
        return (
            self._host_vars.get('ansible_ssh_executable') or
            C.ANSIBLE_SSH_EXECUTABLE
        )

    def timeout(self):
        # TODO: must come from PlayContext too.
        return C.DEFAULT_TIMEOUT

    def ansible_ssh_timeout(self):
        return (
            self._host_vars.get('ansible_timeout') or
            self._host_vars.get('ansible_ssh_timeout') or
            self.timeout()
        )

    def ssh_args(self):
        return [
            mitogen.core.to_text(term)
            for s in (
                (
                    self._host_vars.get('ansible_ssh_args') or
                    getattr(C, 'ANSIBLE_SSH_ARGS', None) or
                    os.environ.get('ANSIBLE_SSH_ARGS')
                    # TODO: ini entry. older versions.
                ),
                (
                    self._host_vars.get('ansible_ssh_common_args') or
                    os.environ.get('ANSIBLE_SSH_COMMON_ARGS')
                    # TODO: ini entry.
                ),
                (
                    self._host_vars.get('ansible_ssh_extra_args') or
                    os.environ.get('ANSIBLE_SSH_EXTRA_ARGS')
                    # TODO: ini entry.
                ),
            )
            for term in ansible.utils.shlex.shlex_split(s)
            if s
        ]

    def become_exe(self):
        return (
            self._host_vars.get('ansible_become_exe') or
            C.DEFAULT_BECOME_EXE
        )

    def sudo_args(self):
        return [
            mitogen.core.to_text(term)
            for s in (
                self._host_vars.get('ansible_sudo_flags') or '',
                self._host_vars.get('ansible_become_flags') or '',
            )
            for term in ansible.utils.shlex.shlex_split(s)
        ]

    def mitogen_via(self):
        return self._host_vars.get('mitogen_via')

    def mitogen_kind(self):
        return self._host_vars.get('mitogen_kind')

    def mitogen_docker_path(self):
        return self._host_vars.get('mitogen_docker_path')

    def mitogen_kubectl_path(self):
        return self._host_vars.get('mitogen_kubectl_path')

    def mitogen_lxc_path(self):
        return self.host_vars.get('mitogen_lxc_path')

    def mitogen_lxc_attach_path(self):
        return self._host_vars.get('mitogen_lxc_attach_path')

    def mitogen_lxc_info_path(self):
        return self._host_vars.get('mitogen_lxc_info_path')

    def mitogen_machinectl_path(self):
        return self._host_vars.get('mitogen_machinectl_path')

    def mitogen_ssh_debug_level(self):
        return self._host_vars.get('mitogen_ssh_debug_level')

    def extra_args(self):
        return []  # TODO
