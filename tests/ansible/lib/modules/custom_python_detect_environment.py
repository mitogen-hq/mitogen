#!/usr/bin/python
# I am an Ansible new-style Python module. I return details about the Python
# interpreter I run within.

from ansible.module_utils.basic import AnsibleModule
from ansible.module_utils.basic import get_module_path

import os
import pwd
import socket
import sys


try:
    all
except NameError:
    # Python 2.4
    def all(it):
        for elem in it:
            if not elem:
                return False
        return True


def main():
    module = AnsibleModule(argument_spec={})
    module.exit_json(
        fs={
            '/tmp': {
                'resolved': os.path.realpath('/tmp'),
            },
        },
        python={
            'version': {
                'full': '%i.%i.%i' % sys.version_info[:3],
                'info': list(sys.version_info),
                'major': sys.version_info[0],
                'minor': sys.version_info[1],
                'patch': sys.version_info[2],
            },
        },
        argv=sys.argv,
        __file__=__file__,
        argv_types_correct=all(type(s) is str for s in sys.argv),
        env=dict(os.environ),
        cwd=os.getcwd(),
        python_path=sys.path,
        pid=os.getpid(),
        ppid=os.getppid(),
        uid=os.getuid(),
        euid=os.geteuid(),
        sys_executable=sys.executable,
        mitogen_loaded='mitogen.core' in sys.modules,
        hostname=socket.gethostname(),
        username=pwd.getpwuid(os.getuid()).pw_name,
        module_tmpdir=getattr(module, 'tmpdir', None),
        module_path=get_module_path(),
    )

if __name__ == '__main__':
    main()
