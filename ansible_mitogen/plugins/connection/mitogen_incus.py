# SPDX-FileCopyrightText: 2019 David Wilson
# SPDX-FileCopyrightText: 2026 Mitogen authors <https://github.com/mitogen-hq>
# SPDX-License-Identifier: BSD-3-Clause
# !mitogen: minify_safe

from __future__ import absolute_import, division, print_function
__metaclass__ = type

import os
import sys

try:
    import ansible_mitogen
except ImportError:
    sys.path.insert(0, os.path.abspath(os.path.join(__file__, '../../../..')))

import ansible_mitogen.connection


class Connection(ansible_mitogen.connection.Connection):
    transport = 'incus'
