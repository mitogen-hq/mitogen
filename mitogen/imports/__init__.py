# SPDX-FileCopyrightText: 2025 Mitogen authors <https://github.com/mitogen-hq>
# SPDX-License-Identifier: BSD-3-Clause
# !mitogen: minify_safe

import sys

if sys.version_info >= (3, 14):
    from mitogen.imports._py314 import _code_imports
elif sys.version_info >= (3, 6):
    from mitogen.imports._py36 import _code_imports
elif sys.version_info >= (2, 5):
    from mitogen.imports._py2 import _code_imports_py25 as _code_imports
else:
    from mitogen.imports._py2 import _code_imports_py24 as _code_imports


def codeobj_imports(co):
    """
    Yield (level, modname, names) tuples by scanning the code object `co`.

    Top level `import mod` & `from mod import foo` statements are matched.
    Those inside a `class ...` or `def ...` block are currently skipped.

    >>> co = compile('import a, b; from c import d, e as f', '<str>', 'exec')
    >>> list(codeobj_imports(co))  # doctest: +ELLIPSIS
    [(..., 'a', ()), (..., 'b', ()), (..., 'c', ('d', 'e'))]

    :return:
        Generator producing `(level, modname, names)` tuples, where:

        * `level`:
            -1 implicit relative (Python 2.x default)
            0  absolute (Python 3.x, `from __future__ import absolute_import`)
            >0 explicit relative (`from . import a`, `from ..b, import c`)
        * `modname`: Name of module to import, or to import `names` from.
        * `names`: tuple of names in `from mod import ..`.
    """
    return _code_imports(co.co_code, co.co_consts, co.co_names)


def stdlib_module_names(version_info=None):
    """
    Return a set of known module names for a Python version.
    """
    if version_info is None:
        version_info = sys.version_info
    if version_info >= (3, 10):
        return sys.stdlib_module_names

    modname = "%s.stdlibs.py%d%d" % (__name__, version_info[0], version_info[1])
    return __import__(modname, None, None, ['']).module_names


def unsuitable_module_names(version_info=None):
    """
    Return a set of module names known to be unsuitable for serving by Mitogen.
    """
    if version_info is None:
        version_info = sys.version_info
    names = set([
        'org',           # Jython, Imported by copy, pickle, & xml.sax.
    ])
    names.update(stdlib_module_names(version_info))
    if version_info >= (3, 0):
        names.update(stdlib_module_names((2, 7)))
    else:
        names.update(stdlib_module_names((3, 6)))
    return names
