#!/usr/bin/env python

import json
import os
import subprocess
import sys

os.environ['ORIGINAL_ARGV'] = json.dumps(sys.argv)
os.environ['THIS_IS_STUB_SUDO'] = '1'

rest_argv = sys.argv[sys.argv.index('--') + 1:]

if os.environ.get('PREHISTORIC_SUDO'):
    # issue #481: old versions of sudo did in fact use execve, thus we must
    # have TTY handle preservation in core.py.
    os.execvp(rest_argv[0], rest_argv)
else:
    # This must be a child process and not exec() since Mitogen replaces its
    # stderr descriptor, causing the last user of the slave PTY to close it,
    # resulting in the master side indicating EIO.
    subprocess.check_call(rest_argv)
