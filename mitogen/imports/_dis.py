import dis
import itertools
import sys
from types import CodeType

IMPORT_NAME = dis.opname.index('IMPORT_NAME')
LOAD_CONST = dis.opname.index('LOAD_CONST')

def _oparg(i, nextb):
    if i >= dis.HAVE_ARGUMENT:
        return nextb() | (nextb() << 8)


def instructions(co):
    "Yield `(op, oparg)` tuples for bytecode in the code object `co`."
    ordit = (ord(c) for c in co.co_code)
    return ((i, _oparg(i, ordit.next)) for i in ordit)


def window(it, n):
    its = tuple(itertools.tee(iter(it), n))
    for i, it in enumerate(its[1:]):
        next(itertools.islice(it, i+1, i+1), None)
    return itertools.izip(*its)


def scan_imports(source, filename='<str>'):
    "Yield `(level, name, fromnames)` tuples for imports in `source`"
    co = compile(source, filename, 'exec')
    if sys.version_info >= (2, 5): return _py25_codeobj_imports(co)
    else: return _py24_codeobj_imports(co)


def _py25_codeobj_imports(co):
    for (op1, arg1), (op2, arg2), (op3, arg3) in window(instructions(co), 3):
        if op1 == op2 == LOAD_CONST and op3 == IMPORT_NAME:
            yield (co.co_consts[arg1], co.co_names[arg3], co.co_consts[arg2] or ())

        elif op1 == LOAD_CONST and isinstance(co.co_consts[arg1], CodeType):
            for tup in _py25_codeobj_imports(co.co_consts[arg1]): yield tup


def _py24_codeobj_imports(co):
    for (op1, arg1), (op2, arg2) in window(instructions(co), 2):
        if op1 == LOAD_CONST and op2 == IMPORT_NAME:
            yield (-1, co.co_names[arg2], co.co_consts[arg1] or ())

        elif op1 == LOAD_CONST and isinstance(co.co_consts[arg1], CodeType):
            for tup in _py25_codeobj_imports(co.co_consts[arg1]): yield tup
