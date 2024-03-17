#!/usr/bin/python
# -*- coding: utf-8 -*-

# (c) 2012, Michael DeHaan <michael.dehaan@gmail.com>
# (c) 2016, Toshio Kuratomi <tkuratomi@ansible.com>
# (c) 2020, Steven Robertson <srtrumpetaggie@gmail.com>
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)

from __future__ import absolute_import, division, print_function
__metaclass__ = type

import os
import platform
import sys
from ansible.module_utils.basic import AnsibleModule


def main():
    module = AnsibleModule(argument_spec=dict(
        facts_copy=dict(type=dict, default={}),
        facts_to_override=dict(type=dict, default={})
    ))

    # revert the Mitogen OSX tweak since discover_interpreter() doesn't return this info
    # NB This must be synced with mitogen.parent.Connection.get_boot_command()
    platform_release_major = int(platform.release().partition('.')[0])
    if sys.modules.get('mitogen') and sys.platform == 'darwin':
        if platform_release_major < 19 and sys.executable == '/usr/bin/python2.7':
            sys.executable = '/usr/bin/python'
        if platform_release_major in (20, 21) and sys.version_info[:2] == (2, 7):
            # only for tests to check version of running interpreter -- Mac 10.15+ changed python2
            # so it looks like it's /usr/bin/python but actually it's /System/Library/Frameworks/Python.framework/Versions/2.7/Resources/Python.app/Contents/MacOS/Python
            sys.executable = "/usr/bin/python"

    facts_copy = module.params['facts_copy']
    discovered_interpreter_python = facts_copy['discovered_interpreter_python']
    result = {
        'changed': False,
        'ansible_facts': module.params['facts_to_override'],
        'discovered_and_running_samefile': os.path.samefile(
            os.path.realpath(discovered_interpreter_python),
            os.path.realpath(sys.executable),
        ),
        'discovered_python': {
            'as_seen': discovered_interpreter_python,
            'resolved': os.path.realpath(discovered_interpreter_python),
        },
        'running_python': {
            'platform': {
                'release': {
                    'major': platform_release_major,
                },
            },
            'sys': {
                'executable': {
                    'as_seen': sys.executable,
                    'resolved': os.path.realpath(sys.executable),
                },
                'platform': sys.platform,
                'version_info': {
                    'major': sys.version_info[0],
                    'minor': sys.version_info[1],
                },
            },
        },
    }

    module.exit_json(**result)


if __name__ == '__main__':
    main()