# I am an Ansible new-style Python module, but I lack an interpreter.

import sys

# This is the magic marker Ansible looks for:
# from ansible.module_utils.


def usage():
    sys.stderr.write('Usage: %s <input.json>\n' % (sys.argv[0],))
    sys.exit(1)

input_json = sys.stdin.read()

print("{")
print("  \"changed\": false,")
print("  \"msg\": \"Here is my input\",")
print("  \"input\": [%s]" % (input_json,))
print("}")

# Ansible since 2.7.0/52449cc01a7 broke __file__ and *requires* the module
# process to exit itself. So needless.
sys.exit(0)
