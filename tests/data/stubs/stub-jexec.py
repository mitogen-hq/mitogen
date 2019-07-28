#!/usr/bin/env python

import json
import os
import subprocess
import sys

os.environ['ORIGINAL_ARGV'] = json.dumps(sys.argv)
os.environ['THIS_IS_STUB_JEXEC'] = '1'

# This must be a child process and not exec() since Mitogen replaces its stderr
# descriptor, causing the last user of the slave PTY to close it, resulting in
# the master side indicating EIO.
subprocess.call(sys.argv[sys.argv.index('somejail') + 1:])
os._exit(0)
