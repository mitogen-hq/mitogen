# SPDX-FileCopyrightText: 2026 Mitogen authors <https://github.com/mitogen-hq>
# SPDX-License-Identifier: BSD-3-Clause
# !mitogen: minify_safe

from __future__ import absolute_import, division, print_function
__metaclass__ = type

import platform

from ansible.module_utils.basic import AnsibleModule


DOCUMENTATION = '''
module: platform_facts
short_description: Gather minimal facts about the platform OS/architecture
description:
    - Gather minimal facts about the OS and archtecture, without initiating
      network requests or use of the socket module.
notes:
    - This module avoids delays to playbook execution caused by attempting DNS
      or mDNS queries for ansible_facts.fqdn et al. On macOS >= 15 they appear
      to get delayed/blocked by Local Network/TCC privacy restrictions.
      See https://github.com/mitogen-hq/mitogen/issues/1545.
attributes:
    check_mode:
        support: full
    facts:
        support: full
author:
    - Alex Willmer
'''


def main():
    module = AnsibleModule(argument_spec={}, supports_check_mode=True)

    ansible_facts = dict(
        kernel_version=platform.version(),
        kernel= platform.release(),
        machine=platform.machine(),
        nodename=platform.node(),
        python_version=platform.python_version(),
        system=platform.system(),
    )

    module.exit_json(
        ansible_facts=ansible_facts,
        changed=False,
    )


if __name__ == '__main__':
    main()
