#!/usr/bin/python
# issue #590: I am an Ansible new-style Python module that tries to use
# ansible.module_utils.distro.

import ansible
from ansible.module_utils.basic import AnsibleModule

ansible_version = tuple(int(s) for s in ansible.__version__.split('.'))

if ansible_version[:2] >= (2, 8):
    from ansible.module_utils import distro
else:
    distro = None

def main():
    module = AnsibleModule(argument_spec={})
    if ansible_version[:2] >= (2, 8):
        module.exit_json(info=distro.info())
    else:
        module.exit_json(info={'id': None})

if __name__ == '__main__':
    main()
