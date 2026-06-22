# SPDX-FileCopyrightText: 2026 Mitogen authors <https://github.com/mitogen-hq>
# SPDX-License-Identifier: BSD-3-Clause
# !mitogen: minify_safe

import dis
import opcode

IMPORT_NAME = opcode.opmap['IMPORT_NAME']
LOAD_COMMON_CONSTANT = opcode.opmap['LOAD_COMMON_CONSTANT']
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
        if (
            code[op3_idx-4] != LOAD_SMALL_INT
            or (op2 := code[op3_idx-2]) not in {LOAD_COMMON_CONSTANT, LOAD_CONST}
        ):
            start = op3_idx + 2
            continue
        start = op3_idx + 6
        arg1, arg2, arg3 = code[op3_idx-3], code[op3_idx-1], code[op3_idx+1]
        if op2 == LOAD_COMMON_CONSTANT:
            yield (arg1, names[arg3>>2], opcode._common_constants[arg2] or ())
        elif op2 == LOAD_CONST:
            yield (arg1, names[arg3>>2], consts[arg2] or ())


def _codeobj_imports(co):
    instrs = list(dis.get_instructions(co))
    for i, instr in enumerate(instrs):
        if instr.opcode != IMPORT_NAME:
            continue
        print(instr)