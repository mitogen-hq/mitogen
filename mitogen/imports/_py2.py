# SPDX-FileCopyrightText: 2025 Mitogen authors <https://github.com/mitogen-hq>
# SPDX-License-Identifier: BSD-3-Clause
# !mitogen: minify_safe

import array
import imp
import itertools
import opcode
import sys


IMPORT_NAME = opcode.opmap['IMPORT_NAME']
LOAD_CONST = opcode.opmap['LOAD_CONST']


class MiniSpec(object):
    __slots__ = (
        'name',
        'loader',
        'origin',
        'loader_state',
        'submodule_search_locations',
    )

    def __init__(
            self, name, loader, origin=None, loader_state=None, is_package=None,
    ):
        self.name = name
        self.loader = loader
        self.origin = origin
        self.loader_state = loader_state
        self.submodule_search_locations = bool(is_package) and [] or None

    def parent(self):
        if self.submodule_search_locations is None:
            return self.name.rsplit(self.name, 1)[0]
        else:
            return self.name

    def __repr__(self):
        return '%s(name=%r, loader=%r, origin=%r, submodule_search_locations=%r)' % (
            type(self).__name__,
            self.name,
            self.loader,
            self.origin,
            self.submodule_search_locations,
        )


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


def _resolve_implicit_relative(level, modname, pkgname):
    """
    Return fullname of module by trying relative name first or absolute name
    if that fails
    """
    if level != -1:
        raise ValueError("Expected level == -1, got: %d" % (level,))
    if not modname:
        raise ValueError("Module name required, got: %r" % (modname,))
    if not pkgname:
        raise ValueError("Full package name required, got: %r" % (pkgname,))

    # By definition packages specify submodule search paths in pkg.__path__.
    # If pkg.__path__ is absent, then pkgname refers to regular module.
    # A relative import is impossible, so treat modname as an absolute import.
    pkg = sys.modules[pkgname]
    try:
        submodule_search_locations = pkg.__path__
    except AttributeError:
        return modname

    if (
        not isinstance(submodule_search_locations, list)
        or len(submodule_search_locations) != 1
    ):
        raise ValueError(
            'Invalid submodule search locations %r of %r resolving %r'
            % (submodule_search_locations, pkg, modname, ),
        )

    # Search for top level of modname in submodule search locations of pkg.
    # If <pkgname>.<modhead> isn't found, then <pkgname>.<modname> can't exist.
    # A relative import is impossible, so treat modname as an absolute import.
    modhead = modname.split('.', 1)[0]
    try:
        tup = imp.find_module(modhead, submodule_search_locations)
    except ImportError:
        return modname

    # TODO Avoid throwing away this information?
    file, origin, description = tup
    if file:
        file.close()

    return '%s.%s' % (pkgname, modname)