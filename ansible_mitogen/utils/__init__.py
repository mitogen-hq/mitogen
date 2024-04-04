from __future__ import absolute_import, division, print_function
__metaclass__ = type

import re

import ansible

__all__ = [
    'ansible_version',
]


def _parse(v_string):
    # Adapted from distutils.version.LooseVersion.parse()
    component_re = re.compile(r'(\d+ | [a-z]+ | \.)', re.VERBOSE)
    for component in component_re.split(v_string):
        if not component or component == '.':
            continue
        try:
            yield int(component)
        except ValueError:
            yield component


ansible_version = tuple(_parse(ansible.__version__))

del _parse
del re
del ansible
