# issue #590: this module imports a module that replaces itself in sys.modules
# during initialization.
import simple_pkg.replaces_self

def subtract_one(n):
    return simple_pkg.replaces_self.subtract_one(n)
