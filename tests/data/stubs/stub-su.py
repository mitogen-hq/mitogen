#!/usr/bin/env python

import json
import os
import sys
import time

# #363: old input loop would fail to spot auth failure because of scheduling
# vs. su calling write() twice.
if 'DO_SLOW_AUTH_FAILURE' in os.environ:
    os.write(2, u'su: '.encode())
    time.sleep(0.5)
    os.write(2, u'incorrect password\n'.encode())
    os._exit(1)


os.environ['ORIGINAL_ARGV'] = json.dumps(sys.argv)
os.environ['THIS_IS_STUB_SU'] = '1'

# This must be a child process and not exec() since Mitogen replaces its stderr
# descriptor, causing the last user of the slave PTY to close it, resulting in
# the master side indicating EIO.
os.execlp('sh', 'sh', '-c', sys.argv[sys.argv.index('-c') + 1])
