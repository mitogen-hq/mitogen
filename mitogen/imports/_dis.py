# SPDX-FileCopyrightText: 2025 Mitogen authors <https://github.com/mitogen-hq>
# SPDX-License-Identifier: MIT
# !mitogen: minify_safe

import dis
import sys

from mitogen._more_itertools import sliding_window, transpose

IMPORT_NAME = dis.opmap['IMPORT_NAME']
LOAD_CONST = dis.opmap['LOAD_CONST']
LOAD_SMALL_INT = dis.opmap.get('LOAD_SMALL_INT')  # Python >= 3.14


def _instrs_py34(co):
    return ((i.opcode, i.arg) for i in dis.get_instructions(co))


def _op_arg_py24(op, nexti):
    if op >= dis.HAVE_ARGUMENT:
        return nexti() | (nexti() << 8)


def _instrs_py24(co):
    it = (ord(c) for c in co.co_code)
    return ((i, _op_arg_py24(i, it.next)) for i in it)


def _import_py314(co_consts, co_names, arg1, arg2, arg3):
    return (arg1, co_names[arg3], co_consts[arg2] or ())


def _import_py25(co_consts, co_names, arg1, arg2, arg3):
    return (co_consts[arg1], co_names[arg3], co_consts[arg2] or ())


def _import_py24(co_consts, co_names, arg1, arg2):
    return (-1, co_names[arg2], co_consts[arg1] or ())


_OPS_DISPATCH = {
    (LOAD_CONST, IMPORT_NAME): _import_py24,
    (LOAD_CONST, LOAD_CONST, IMPORT_NAME): _import_py25,
    (LOAD_SMALL_INT, LOAD_CONST, IMPORT_NAME): _import_py314,
}


def _imports(co, instrs, size, dispatch=_OPS_DISPATCH):
    ops_args = (transpose(window) for window in sliding_window(instrs, size))
    for ops, args in ops_args:
        try:
            import_fn = dispatch[ops]
        except KeyError:
            continue
        yield import_fn(co.co_consts, co.co_names, *args)


def scan_code_imports(co):
    """
    Yield (level, modname, names) tuples by scanning  the code object `co`.

    Top level ``import ..`` and ``from .. import ..`` statements are matched.
    Those inside a ``class ...`` or ``def ...`` block are currently skipped.

    >>> co = compile('import a, b; from c import d, e as f', '<str>', 'exec')
    >>> list(scan_code_imports(co))  # doctest: +ELLIPSIS
    [(..., 'a', ()), (..., 'b', ()), (..., 'c', ('d', 'e'))]

    :return:
        Generator producing `(level, modname, names)` tuples, where:

        * `level`: -1 for implicit import, 0 for explicit absolute import,
          and >0 for explicit relative import.
        * `modname`: Name of module to import, or import `names` from.
        * `names`: tuple of names in a `from modname import ..` statement.
    """
    if sys.version_info >= (3, 4):
        return _imports(co, _instrs_py34(co), 3)
    if sys.version_info >= (2, 5):
        return _imports(co, _instrs_py24(co), 3)
    if sys.version_info >= (2, 4):
        return _imports(co, _instrs_py24(co), 2)
