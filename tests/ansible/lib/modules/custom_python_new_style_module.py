#!/usr/bin/python
# I am an Ansible new-style Python module. I should receive an encoding string.
# See also custom_python_new_style_module, we should be updated in tandem.

import io
import json
import select
import signal
import sys
import warnings

# Ansible 2.7 changed how new style modules are invoked. It seems that module
# parameters are *sometimes* read before the module runs. Modules that try
# to read directly from stdin, such as this, are unable to. However it doesn't
# always fail, influences seem to include Ansible & Python version. As noted
# in ansible.module_utils.basic._load_params() we should probably use that.
# I think (medium confidence) I narrowed the inflection (with git bisect) to
# https://github.com/ansible/ansible/commit/52449cc01a71778ef94ea0237eed0284f5d75582

# This is the magic marker Ansible looks for:
# from ansible.module_utils.

# These timeouts should prevent hard-to-attribute, 2+ hour CI job timeouts.
# Previously this module has waited on stdin forever (timeoutInMinutes=120).
SELECT_TIMEOUT = 5.0    # seconds
SIGNAL_TIMEOUT = 10     # seconds


def fail_json(msg, **kwargs):
    kwargs.update(failed=True, msg=msg)
    print(json.dumps(kwargs, sys.stdout, indent=2, sort_keys=True))
    sys.exit(1)


def sigalrm_handler(signum, frame):
    fail_json("Still executing after SIGNAL_TIMEOUT=%ds" % (SIGNAL_TIMEOUT,))


def usage():
    sys.stderr.write('Usage: %s <input.json>\n' % (sys.argv[0],))
    sys.exit(1)


# Wait SIGNAL_TIMEOUT seconds, exit with failure if still running.
signal.signal(signal.SIGALRM, sigalrm_handler)
signal.alarm(SIGNAL_TIMEOUT)

# Wait SELECT_TIMEOUT seconds, exit with failure if no data appears on stdin.
# TODO Combine select() & read() in a loop, to handle slow trickle of data.
#      Consider buffering, line buffering, `f.read()` vs `f.read1()`.
# TODO Document that sys.stdin may be a StringIO under Ansible + Mitogen.
try:
    inputs_ready, _, _ = select.select([sys.stdin], [], [], SELECT_TIMEOUT)
except (AttributeError, TypeError, io.UnsupportedOperation) as exc:
    # sys.stdin.fileno() doesn't exist or can't return a real file descriptor.
    warnings.warn("Could not wait on sys.stdin=%r: %r" % (sys.stdin, exc))
else:
    if not inputs_ready:
        fail_json("Gave up waiting on sys.stdin after SELECT_TIMEOUT=%ds"
                  % (SELECT_TIMEOUT,))

# Read all data on stdin. May block forever, if EOF is not reached.
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
