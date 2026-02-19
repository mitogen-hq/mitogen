# SPDX-FileCopyrightText: 2026 Mitogen authors <https://github.com/mitogen-hq>
# SPDX-License-Identifier: BSD-3-Clause

from __future__ import absolute_import, division, print_function
__metaclass__ = type

from ansible.module_utils.basic import AnsibleModule
from ansible_collections.community.general.plugins.module_utils.source_control import bitbucket


def main():
    module = AnsibleModule(argument_spec={})
    module.exit_json()


if __name__ == '__main__':
    main()
