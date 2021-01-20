from distutils.version import LooseVersion

import ansible

__all__ = [
    'ansible_version',
]

if isinstance(ansible.__version__, tuple):
    ansible_version = ansible.__version__
else:
    ansible_version = tuple(LooseVersion(ansible.__version__).version)

del LooseVersion
del ansible
