#!/usr/bin/env python
# I am an Ansible new-style Python module. I should receive an encoding string.

import sys

# This is the magic marker Ansible looks for:
# from ansible.module_utils.


def usage():
    sys.stderr.write('Usage: %s <input.json>\n' % (sys.argv[0],))
    sys.exit(1)

input_json = sys.stdin.read()

print("{")
print("  \"changed\": false,")
# v2.5.1. apt.py started depending on this.
# https://github.com/dw/mitogen/issues/210
print("  \"__file__\": \"%s\"," % (__file__,))
# Python sets this during a regular import.
print("  \"__package__\": \"%s\"," % (__package__,))
print("  \"msg\": \"Here is my input\",")
print("  \"input\": [%s]" % (input_json,))
print("}")

# Ansible since 2.7.0/52449cc01a7 broke __file__ and *requires* the module
# process to exit itself. So needless.
sys.exit(0)
