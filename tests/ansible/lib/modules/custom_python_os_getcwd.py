#!/usr/bin/python
# #591: call os.getcwd() before AnsibleModule ever gets a chance to fix up the
# process environment.

import os

try:
    import json
except ImportError:
    import simplejson as json

print(json.dumps({
    'cwd': os.getcwd()
}))
