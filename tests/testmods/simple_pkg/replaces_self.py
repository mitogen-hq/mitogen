# issue #590: this module replaces itself in sys.modules during initialization.
import sys
import testmods.simple_pkg.b
sys.modules[__name__] = testmods.simple_pkg.b
