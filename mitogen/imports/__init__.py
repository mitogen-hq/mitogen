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
