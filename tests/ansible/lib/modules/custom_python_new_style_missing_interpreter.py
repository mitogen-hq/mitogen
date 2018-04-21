# I am an Ansible new-style Python module, but I lack an interpreter.

import json
import sys

# This is the magic marker Ansible looks for:
# from ansible.module_utils.


def usage():
    sys.stderr.write('Usage: %s <input.json>\n' % (sys.argv[0],))
    sys.exit(1)

# Also must slurp in our own source code, to verify the encoding string was
# added.
with open(sys.argv[0]) as fp:
    me = fp.read()

input_json = sys.stdin.read()

print "{"
print "  \"changed\": false,"
print "  \"msg\": \"Here is my input\","
print "  \"source\": [%s]," % (json.dumps(me),)
print "  \"input\": [%s]" % (input_json,)
print "}"
