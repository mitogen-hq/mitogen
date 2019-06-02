# issue #590: this module replaces itself in sys.modules during initialization.
import sys
import simple_pkg.b
sys.modules[__name__] = simple_pkg.b
