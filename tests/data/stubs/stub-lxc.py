#!/usr/bin/env python

import sys
import os

# setns.py fetching leader PID.
if sys.argv[1] == 'info':
    print('Pid: 1')
    sys.exit(0)

os.environ['ORIGINAL_ARGV'] = repr(sys.argv)
os.environ['THIS_IS_STUB_LXC'] = '1'
os.execv(sys.executable, sys.argv[sys.argv.index('--') + 1:])
