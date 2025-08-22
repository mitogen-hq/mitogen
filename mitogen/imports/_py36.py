# SPDX-FileCopyrightText: 2025 Mitogen authors <https://github.com/mitogen-hq>
# SPDX-License-Identifier: MIT
# !mitogen: minify_safe

import opcode

IMPORT_NAME = opcode.opmap['IMPORT_NAME']
LOAD_CONST = opcode.opmap['LOAD_CONST']
OPS_WINDOW = bytes([LOAD_CONST, LOAD_CONST, IMPORT_NAME])


def _code_imports(code, consts, names, start=0):
    ops, args = code[::2], code[1::2]
    while True:
        start = ops.find(OPS_WINDOW, start)
        if start == -1:
            return
        arg1, arg2, arg3 = args[start], args[start+1], args[start+2]
        yield (consts[arg1], names[arg3], consts[arg2] or ())
        start += 3
