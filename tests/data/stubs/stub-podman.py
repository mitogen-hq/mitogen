#!/usr/bin/env python

import sys
import os

os.environ['ORIGINAL_ARGV'] = repr(sys.argv)
os.environ['THIS_IS_STUB_PODMAN'] = '1'
os.execv(sys.executable, sys.argv[sys.argv.index('--') + 2:])
