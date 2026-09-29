# SPDX-FileCopyrightText: 2025 Mitogen authors <https://github.com/mitogen-hq>
# SPDX-License-Identifier: BSD-3-Clause
# !mitogen: minify_safe

import sys

if sys.version_info >= (3, 4):
    from importlib.machinery import ModuleSpec
    from mitogen.imports._py3 import _resolve_implicit_relative
else:
    from mitogen.imports._py2 import _resolve_implicit_relative
    from mitogen.imports._py2 import MiniSpec as ModuleSpec

if sys.version_info >= (3, 15):
    from mitogen.imports._py315 import _code_imports
elif sys.version_info >= (3, 14):
    from mitogen.imports._py314 import _code_imports
elif sys.version_info >= (3, 6):
    from mitogen.imports._py36 import _code_imports
elif sys.version_info >= (2, 5):
    from mitogen.imports._py2 import _code_imports_py25 as _code_imports
else:
    from mitogen.imports._py2 import _code_imports_py24 as _code_imports


def codeobj_imports(co):
    """
    Yield (level, modname, fromnames) tuples for imports in code object `co`.

    Imports at module (global) scope are included. Imports at local scope are
    currently ignored, this may change in a future version.

    | Import statement          | Tuple (Python 3.x)        |
    | ------------------------- | ------------------------- |
    | `import a`                | `(0, 'a',   ())`          |
    | `import a.b`              | `(0, 'a.b', ())`          |
    | `from a import *`         | `(0, 'a',   ('*',))`      |
    | `from a import b`         | `(0, 'a',   ('b',))`      |
    | `from . import c`         | `(1, '',    ('c',))`      |
    | `from .. import d`        | `(2, '',    ('d',))`      |
    | `from .e import f`        | `(1, 'e',   ('f',))`      |
    | `from ..g.h import i`     | `(2, 'g.h', ('i',))`      |

    >>> co = compile('import a, b; from c import d, e as f', '<str>', 'exec')
    >>> list(codeobj_imports(co))  # doctest: +ELLIPSIS
    [(..., 'a', ()), (..., 'b', ()), (..., 'c', ('d', 'e'))]

    :return:
        Generator producing `(level, modname, names)` tuples, where:

        * `level`:
            -1 implicit relative (Python 2.x default)
            0  absolute (Python 3.x, `from __future__ import absolute_import`)
            >0 explicit relative (`from . import a`, `from ..b, import c`)
        * `modname`: Name of module to import.
        * `fromnames`: tuple of names in `from mod import name1, name2, ...`.
    """
    return _code_imports(co.co_code, co.co_consts, co.co_names)


def flatten_imports(it):
    """
    Yield `(level, name)` tuples from an iterable of
    `(level, modname, fromnames)` tuples.

    Flattening `modname` & `fromnames` destroys some information in the input.
    Given `import a.b` we can conclude `a.b` refers to a module; but
    `from c import d` is ambiguous, `c.d` may refer to a module or e.g. a class.

    `import x.y` produces input tuple `(..., 'x.y', ())`; `from x import y`
    produces input tuple `(..., 'x', ('y',))` both produce output the same
    flattened tuple `(..., 'x.y')`.

    >>> list(flatten_imports([(0, 'a', ()), (0, 'b', ('c', 'd'))]))
    [(0, 'a'), (0, 'b.c'), (0, 'b.d')]
    """
    for level, modname, fromnames in it:
        for fromname in fromnames:
            yield (level, '%s.%s' % (modname, fromname))
        if not fromnames:
            yield (level, modname)


def parent_modnames(modname):
    """
    Yield parent names of module named `modname` in decending order.

    >>> list(parent_modnames('foo.bar.baz.quux'))
    ['foo', 'foo.bar', 'foo.bar.baz']
    """
    pos = -1
    while True:
        pos = modname.find('.', pos+1)
        if pos < 0: break
        yield modname[:pos]


def _resolve_explicit_relative(level, modname, pkgname):
    """
    Return the fullname of module with name `modname`, relative to the fullname
    `pkgname`.

    >>> resolve_relative_name(1, '', 'foo.bar')
    'foo.bar'
    >>> resolve_relative_name(2, 'quux', 'foo.bar')
    'foo.quux'
    """
    if level <= 0:
        raise ValueError("Expected relative level >= 1, got: %d" % (level,))
    if not pkgname:
        raise ValueError("Full package name required, got: %s" % (pkgname,))

    pkgbits = pkgname.rsplit('.', level - 1)
    if len(pkgbits) < level:
        raise ImportError(
            "Level %d import of module %s in %s would go beyond top-level"
            % (level, modname, pkgname)
        )
    pkgbase = pkgbits[0]
    if modname:
        return '%s.%s' % (pkgbase, modname)
    else:
        return pkgbase


def resolve(level, modname, pkgname):
    if level == 0:
        return modname
    if level >= 1:
        return _resolve_explicit_relative(level, modname, pkgname)
    if level == -1:
        return _resolve_implicit_relative(level, modname, pkgname)
    raise ValueError("Invalid import level: %r" % (level,))


def top_level_name(fullname):
    """
    >>> top_level_name('foo.bar')
    'foo'
    >>> top_level_name('foo')
    'foo'
    """
    return fullname.partition('.')[0]


class ModuleName(object):
    __slots__ = ('_raw_name')

    def __init__(self, name):
        self._raw_name = str(name)

    @property
    def top_level(self): return self._raw_name.partition('.')[0]

    @property
    def parts(self): return self._raw_name.split('.')

    def __eq__(self, other): return str(self) == str(other)
    def __hash__(self): return hash(self._raw_name)

    def __str__(self): return self._raw_name
    def __repr__(self): return '%s(%r)' % (type(self).__name__, self._raw_name)

