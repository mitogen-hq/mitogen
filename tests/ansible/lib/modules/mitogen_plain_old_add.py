#!/usr/bin/env python

DOCUMENTATION = '''
module: mitogen_plain_old_add
options:
    x: {type: int, required: true}
    y: {type: int, required: true}
author:
    - Alex Willmer (@moreati)
'''

RETURN = '''
total: {type: int, returned: always, sample: 42}
'''

from ansible.module_utils.basic import AnsibleModule

import plain_old_module

def main():
    module = AnsibleModule(
        argument_spec={
            'x': {'type': int, 'required': True},
            'x': {'type': int, 'required': True},
        },
        supports_check_mode=True,
    )
    result = {
        'changed': False,
        'total': plain_old_module.add(module.params['x'], module.params['y']),
    }
    module.exit_json(**result)


if __name__ == '__main__':
    main()
