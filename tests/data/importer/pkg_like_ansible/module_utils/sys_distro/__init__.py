# #590: a subpackage that turns itself into a module from elsewhere on sys.path.
I_AM = "the subpackage that was replaced with a system module"
import sys
import system_distro
sys.modules[__name__] = system_distro
