#!/usr/bin/env python
import os
import subprocess

import ci_lib

os.chdir(ci_lib.IMAGE_PREP_DIR)
subprocess.check_call('ansible-playbook -c local -i localhost, _user_accounts.yml'.split())
subprocess.check_call('ansible-playbook -c local -i localhost, macos_localhost.yml'.split())
