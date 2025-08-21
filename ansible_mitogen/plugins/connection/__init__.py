import os
import sys

try:
    import ansible_mitogen
except ImportError:
    sys.path.insert(0, os.path.abspath(os.path.join(__file__, '../../../..')))
