#!/usr/bin/env python

import optparse
import os
import shlex
import sys

parser = optparse.OptionParser()
parser.add_option('--user', '-l', action='store')
parser.add_option('-o', dest='options', action='append')
parser.disable_interspersed_args()

opts, args = parser.parse_args(sys.argv[1:])
args.pop(0)  # hostname
args = [''.join(shlex.split(s)) for s in args]
print args
os.execvp(args[0], args)
