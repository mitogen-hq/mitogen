#!/usr/bin/env python

import optparse
import os
import shlex
import subprocess
import sys

parser = optparse.OptionParser()
parser.add_option('--user', '-l', action='store')
parser.add_option('-o', dest='options', action='append')
parser.disable_interspersed_args()

opts, args = parser.parse_args(sys.argv[1:])
args.pop(0)  # hostname

# On Linux the TTY layer appears to begin tearing down a PTY after the last FD
# for it is closed, causing SIGHUP to be sent to its foreground group. Since
# the bootstrap overwrites the last such fd (stderr), we can't just exec it
# directly, we must hold it open just like real SSH would. So use
# subprocess.call() rather than os.execve() here.
args = [''.join(shlex.split(s)) for s in args]
sys.exit(subprocess.call(args))
