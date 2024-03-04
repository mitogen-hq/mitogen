#!/usr/bin/python
# -*- coding: utf-8 -*-

# (c) 2012, Michael DeHaan <michael.dehaan@gmail.com>
# (c) 2016, Toshio Kuratomi <tkuratomi@ansible.com>
# (c) 2020, Steven Robertson <srtrumpetaggie@gmail.com>
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)

from __future__ import absolute_import, division, print_function
__metaclass__ = type

import platform
import sys
from ansible.module_utils.basic import AnsibleModule


def main():
    result = dict(changed=False)

    module = AnsibleModule(argument_spec=dict(
        facts=dict(type=dict, default={})
    ))

    result['ansible_facts'] = module.params['facts']
    # revert the Mitogen OSX tweak since discover_interpreter() doesn't return this info
    if sys.platform == 'darwin' and sys.executable != '/usr/bin/python':
        if int(platform.release()[:2]) < 19:
            sys.executable = sys.executable[:-3]
        else:
            # only for tests to check version of running interpreter -- Mac 10.15+ changed python2
            # so it looks like it's /usr/bin/python but actually it's /System/Library/Frameworks/Python.framework/Versions/2.7/Resources/Python.app/Contents/MacOS/Python
            sys.executable = "/usr/bin/python"
    result['running_python_interpreter'] = sys.executable

    module.exit_json(**result)


if __name__ == '__main__':
    main()