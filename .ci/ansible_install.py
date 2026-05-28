#!/usr/bin/env python
# SPDX-FileCopyrightText: 2026 Mitogen authors <https://github.com/mitogen-hq>
# SPDX-License-Identifier: BSD-3-Clause
from __future__ import absolute_import, division, print_function

import ci_lib
from ci_lib import subprocess

with ci_lib.Fold('ansible_prep'):
    subprocess.check_call(
        ['ansible-galaxy', 'collection', 'install', '-r', ci_lib.ANSIBLE_TESTS_REQUIREMENTS],
    )
