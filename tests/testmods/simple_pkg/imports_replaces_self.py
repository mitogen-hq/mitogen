# issue #590: this module imports a module that replaces itself in sys.modules
# during initialization.
import testmods.simple_pkg.replaces_self

def subtract_one(n):
    return testmods.simple_pkg.replaces_self.subtract_one(n)
