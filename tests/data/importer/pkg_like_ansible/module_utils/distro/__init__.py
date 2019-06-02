# #590: a package that turns itself into a module.
I_AM = "the package that was replaced"
import sys
from pkg_like_ansible.module_utils.distro import _distro
sys.modules[__name__] = _distro
