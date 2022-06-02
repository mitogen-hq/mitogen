#!/usr/bin/env python

import json
import os
import sys

os.environ['ORIGINAL_ARGV'] = json.dumps(sys.argv)
os.environ['THIS_IS_STUB_PYTHON'] = '1'

if sys.argv[1].startswith('-'):
    os.execvp(sys.executable, [sys.executable] + sys.argv[1:])
else:
    os.environ['STUB_PYTHON_FIRST_ARG'] = sys.argv.pop(1)
    os.execvp(sys.executable, sys.argv[1:])
