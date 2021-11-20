from __future__ import absolute_import

import distutils.version

import ansible

__all__ = [
    'ansible_version',
]

ansible_version = tuple(distutils.version.LooseVersion(ansible.__version__).version)
del distutils
del ansible
