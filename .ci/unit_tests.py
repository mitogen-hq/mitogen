#!/usr/bin/env python
# SPDX-FileCopyrightText: 2026 Mitogen authors <https://github.com/mitogen-hq>
# SPDX-License-Identifier: BSD-3-Clause
from __future__ import absolute_import, division, print_function

import sys

import ci_lib
from ci_lib import subprocess

interesting = ci_lib.get_interesting_procs()

with ci_lib.Fold('unit_tests'):
    subprocess.run(
        [
            sys.executable, '-m', 'unittest', 'discover',
            '--start-directory', sys.argv[1],
            '--pattern', '*_test.py',
            '--verbose',
        ],
        check=True,
    )

ci_lib.check_stray_processes(interesting)
