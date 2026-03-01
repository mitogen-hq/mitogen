#!/usr/bin/env python
# SPDX-FileCopyrightText: 2026 Mitogen authors <https://github.com/mitogen-hq>
# SPDX-License-Identifier: BSD-3-Clause
from __future__ import absolute_import, division, print_function

import os

import ci_lib
from ci_lib import subprocess

with ci_lib.Fold('machine_prep'):
    os.chdir(ci_lib.IMAGE_PREP_DIR)
    subprocess.check_call('ansible-playbook -c local -i localhost, _user_accounts.yml'.split())
    subprocess.check_call('ansible-playbook -c local -i localhost, macos_localhost.yml'.split())
