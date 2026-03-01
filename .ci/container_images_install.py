#!/usr/bin/env python
# SPDX-FileCopyrightText: 2026 Mitogen authors <https://github.com/mitogen-hq>
# SPDX-License-Identifier: BSD-3-Clause
from __future__ import absolute_import, division, print_function

import ci_lib

if ci_lib.SKIP_CONTAINER_TESTS:
    raise SystemExit(0)

containers = ci_lib.container_specs(ci_lib.DISTRO_SPECS.split())
ci_lib.pull_container_images(containers)
