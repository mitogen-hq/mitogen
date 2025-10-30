# SPDX-FileCopyrightText: 2025 Mitogen authors <https://github.com/mitogen-hq>
# SPDX-License-Identifier: BSD-3-Clause
# !mitogen: minify_safe

import array
import itertools
import opcode


IMPORT_NAME = opcode.opmap['IMPORT_NAME']
LOAD_CONST = opcode.opmap['LOAD_CONST']


def _opargs(code, _have_arg=opcode.HAVE_ARGUMENT):
    it = iter(array.array('B', code))
    nexti = it.next
    for i in it:
        if i >= _have_arg:
            yield (i, nexti() | (nexti() << 8))
        else:
            yield (i, None)


def _code_imports_py25(code, consts, names):
    it1, it2, it3 = itertools.tee(_opargs(code), 3)
    try:
        next(it2)
        next(it3)
        next(it3)
    except StopIteration:
        return
    for oparg1, oparg2, (op3, arg3) in itertools.izip(it1, it2, it3):
        if op3 != IMPORT_NAME:
            continue
        op1, arg1 = oparg1
        op2, arg2 = oparg2
        if op1 != LOAD_CONST or op2 != LOAD_CONST:
            continue
        yield (consts[arg1], names[arg3], consts[arg2] or ())


def _code_imports_py24(code, consts, names):
    it1, it2 = itertools.tee(_opargs(code), 2)
    try:
        next(it2)
    except StopIteration:
        return
    for oparg1, (op2, arg2) in itertools.izip(it1, it2):
        if op2 != IMPORT_NAME:
            continue
        op1, arg1 = oparg1
        if op1 != LOAD_CONST:
            continue
        yield (-1, names[arg2], consts[arg1] or ())
