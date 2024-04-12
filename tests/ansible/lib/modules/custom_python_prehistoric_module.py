#!/usr/bin/python

# Test functionality of ansible_mitogen.runner.PREHISTORIC_HACK_RE, which
# removes `reload(sys); sys.setdefaultencoding(...)` from an Ansible module
# as it is sent to a target. There are probably very few modules in the wild
# that still do this, reload() is a Python 2.x builtin function.
# issue #555: I'm a module that cutpastes an old hack.

from ansible.module_utils.basic import AnsibleModule

import sys
reload(sys)
sys.setdefaultencoding('utf8')


def main():
    module = AnsibleModule(argument_spec={})
    module.exit_json(ok=True)

if __name__ == '__main__':
    main()
