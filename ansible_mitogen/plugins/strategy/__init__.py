# SPDX-FileCopyrightText: 2025 Mitogen authors <https://github.com/mitogen-hq>
# SPDX-License-Identifier: BSD-3-Clause
# !mitogen: minify_safe

import os
import sys

try:
    import ansible_mitogen
except ImportError:
    sys.path.insert(0, os.path.abspath(os.path.join(__file__, '../../../..')))
