import distutils.version

import ansible

__all__ = [
    'ansible_version',
]

if isinstance(ansible.__version__, tuple):
    ansible_version = ansible.__version__
else:
    ansible_version = tuple(distutils.version.LooseVersion(ansible.__version__).version)
