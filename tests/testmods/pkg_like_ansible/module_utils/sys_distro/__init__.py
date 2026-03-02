# #590: a subpackage that turns itself into a module from elsewhere on sys.path.
I_AM = "the subpackage that was replaced with a system module"
import sys
import testmod_system_distro
sys.modules[__name__] = testmod_system_distro
