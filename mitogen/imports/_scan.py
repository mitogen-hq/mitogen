# SPDX-FileCopyrightText: 2025 Mitogen authors <https://github.com/mitogen-hq>
# SPDX-License-Identifier: MIT
# !mitogen: minify_safe

import opcode
import re
import struct
import sys

from mitogen._more_itertools import sliding_window, transpose


OP_IMPORT_NAME = b'%c' % opcode.opmap['IMPORT_NAME']
OP_LOAD_CONST = b'%c' % opcode.opmap['LOAD_CONST']


if sys.version_info >= (3, 6):
    _INSTR_PATT = re.compile(br'(.)(.)', re.DOTALL)

    def _arg(s):
        return s[0]

    def _instrs(co):
        return (m.groups() for m in _INSTR_PATT.finditer(co.co_code))
else:
    _INSTR_PATT = re.compile(
        br'([\x00-\x%x]) | ([\x%x-\xff])(..)'
        % (opcode.HAVE_ARGUMENT-1, opcode.HAVE_ARGUMENT),
        re.DOTALL|re.VERBOSE,
    )

    def _arg(s, unpack=struct.Struct('<H').unpack):
        arg, = unpack(s)
        return arg

    def _instrs(co):
        for m in _INSTR_PATT.finditer(co.co_code):
            op_noarg, op_have_arg, arg = m.groups()
            yield op_noarg and (op_noarg, None) or (op_have_arg, arg)


if sys.version_info >= (3, 14):
    _WINDOW_SIZE = 3
    OP_LOAD_SMALL_INT = b'%c' % opcode.opmap['LOAD_SMALL_INT']

    def _global_import(co_consts, co_names, arg1, arg2, arg3):
        return (arg1, co_names[arg3], co_consts[arg2] or ())

    _OPS_DISPATCH = {
        (OP_LOAD_SMALL_INT, OP_LOAD_CONST, OP_IMPORT_NAME): _global_import,
    }
elif sys.version_info >= (2, 5):
    _WINDOW_SIZE = 3

    def _global_import(co_consts, co_names, arg1, arg2, arg3):
        return (co_consts[arg1], co_names[arg3], co_consts[arg2] or ())

    _OPS_DISPATCH = {
        (OP_LOAD_CONST, OP_LOAD_CONST, OP_IMPORT_NAME): _global_import,
    }
else:
    def _global_import(co_consts, co_names, arg1, arg2):
        return (-1, co_names[arg2], co_consts[arg1] or ())

    _OPS_DISPATCH = {
         (OP_LOAD_CONST, OP_IMPORT_NAME): _global_import,
    }


def _scan(co, instrs, size=_WINDOW_SIZE, dispatch=_OPS_DISPATCH):
    ops_args = (transpose(window) for window in sliding_window(instrs, size))
    for ops, args in ops_args:
        try:
            import_fn = dispatch[ops]
        except KeyError:
            continue
        yield import_fn(co.co_consts, co.co_names, *(_arg(a) for a in args))


def scan_code_imports(co):
    """
    Yield (level, modname, names) tuples by scanning the code object `co`.

    Top level `import mod` & `from mod import foo` statements are matched.
    Those inside a `class ...` or `def ...` block are currently skipped.

    >>> co = compile('import a, b; from c import d, e as f', '<str>', 'exec')
    >>> list(scan_code_imports(co))  # doctest: +ELLIPSIS
    [(..., 'a', ()), (..., 'b', ()), (..., 'c', ('d', 'e'))]

    :return:
        Generator producing `(level, modname, names)` tuples, where:

        * `level`:
            -1 implicit relative (Python 2.x default)
            0  absolute (Python 3.x, `from __future__ import absolute_import`)
            >0 explicit relative import (`from . import a`)
        * `modname`: Name of module to import, or to import `names` from.
        * `names`: tuple of names in `from mod import ..`, or empty tuple.
    """
    return _scan(co, _instrs(co))
