#!/usr/bin/python
# -*- coding: utf-8 -*-

from __future__ import absolute_import, division, print_function
__metaclass__ = type

import atexit
import errno
import os

from ansible.module_utils.basic import AnsibleModule

CLEANUP_FILE = '/tmp/mitogen_test_atexit_cleanup_canary.txt'


def cleanup(file):
    try:
        os.unlink(file)
    except OSError as exc:
        if exc.errno == errno.ENOENT:
            pass
        raise


def main():
    module = AnsibleModule(
        argument_spec={},
    )

    atexit.register(cleanup, CLEANUP_FILE)

    with open(CLEANUP_FILE, 'wb') as f:
        f.truncate()

    result = {
        'changed': True,
    }
    module.exit_json(**result)



if __name__ == '__main__':
    main()
