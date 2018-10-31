#!/usr/bin/env python

import json
import os
import sys

os.environ['ORIGINAL_ARGV'] = json.dumps(sys.argv)
os.environ['THIS_IS_STUB_SUDO'] = '1'
os.execv(sys.executable, sys.argv[sys.argv.index('--') + 1:])
