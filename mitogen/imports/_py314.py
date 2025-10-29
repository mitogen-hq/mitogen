# SPDX-FileCopyrightText: 2025 Mitogen authors <https://github.com/mitogen-hq>
# SPDX-License-Identifier: BSD-3-Clause
# !mitogen: minify_safe

import opcode

IMPORT_NAME = opcode.opmap['IMPORT_NAME']
LOAD_CONST = opcode.opmap['LOAD_CONST']
LOAD_SMALL_INT = opcode.opmap['LOAD_SMALL_INT']


def _code_imports(code, consts, names):
    start = 4
    while True:
        op3_idx = code.find(IMPORT_NAME, start, -1)
        if op3_idx < 0:
            return
        if op3_idx % 2:
            start = op3_idx + 1
            continue
        if code[op3_idx-4] != LOAD_SMALL_INT or code[op3_idx-2] != LOAD_CONST:
            start = op3_idx + 2
            continue
        start = op3_idx + 6
        arg1, arg2, arg3 = code[op3_idx-3], code[op3_idx-1], code[op3_idx+1]
        yield (arg1, names[arg3], consts[arg2] or ())
