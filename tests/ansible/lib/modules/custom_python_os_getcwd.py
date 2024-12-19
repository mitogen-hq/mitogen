#!/usr/bin/python
# #591: call os.getcwd() before AnsibleModule ever gets a chance to fix up the
# process environment.

import json
import os


print(json.dumps({
    'cwd': os.getcwd()
}))
