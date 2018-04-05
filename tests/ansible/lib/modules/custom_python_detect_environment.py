#!/usr/bin/python
# I am an Ansible new-style Python module. I return details about the Python
# interpreter I run within.

from ansible.module_utils.basic import AnsibleModule

import os
import pwd
import socket
import sys


def main():
    module = AnsibleModule(argument_spec={})
    module.exit_json(
        sys_executable=sys.executable,
        mitogen_loaded='mitogen.core' in sys.modules,
        hostname=socket.gethostname(),
        username=pwd.getpwuid(os.getuid()).pw_name,
    )

if __name__ == '__main__':
    main()
