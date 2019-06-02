#!/usr/bin/python
# issue #590: I am an Ansible new-style Python module that tries to use
# ansible.module_utils.distro.

from ansible.module_utils.basic import AnsibleModule
from ansible.module_utils import distro

def main():
    module = AnsibleModule(argument_spec={})
    module.exit_json(info=distro.info())

if __name__ == '__main__':
    main()
