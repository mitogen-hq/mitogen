# I am an Ansible new-style Python module, but I lack an interpreter.

import sys

# As of Ansible 2.10, Ansible changed new-style detection: # https://github.com/ansible/ansible/pull/61196/files#diff-5675e463b6ce1fbe274e5e7453f83cd71e61091ea211513c93e7c0b4d527d637L828-R980
# NOTE: this import works for Mitogen, and the import below matches new-style Ansible 2.10
# TODO: find out why 1 import won't work for both Mitogen and Ansible
# from ansible.module_utils.
# import ansible.module_utils.


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
