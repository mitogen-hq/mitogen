# Copyright 2019, David Wilson
#
# Redistribution and use in source and binary forms, with or without
# modification, are permitted provided that the following conditions are met:
#
# 1. Redistributions of source code must retain the above copyright notice,
# this list of conditions and the following disclaimer.
#
# 2. Redistributions in binary form must reproduce the above copyright notice,
# this list of conditions and the following disclaimer in the documentation
# and/or other materials provided with the distribution.
#
# 3. Neither the name of the copyright holder nor the names of its contributors
# may be used to endorse or promote products derived from this software without
# specific prior written permission.
#
# THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS"
# AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE
# IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE
# ARE DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT HOLDER OR CONTRIBUTORS BE
# LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR
# CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF
# SUBSTITUTE GOODS OR SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS
# INTERRUPTION) HOWEVER CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN
# CONTRACT, STRICT LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE)
# ARISING IN ANY WAY OUT OF THE USE OF THIS SOFTWARE, EVEN IF ADVISED OF THE
# POSSIBILITY OF SUCH DAMAGE.

from __future__ import absolute_import, division, print_function
from __future__ import unicode_literals
__metaclass__ = type

import collections
import logging
import os
import re
import sys

try:
    # Python >= 3.4, PEP 451 ModuleSpec API
    import importlib.machinery
    import importlib.util
except ImportError:
    # Python < 3.4, PEP 302 Import Hooks
    import imp

import mitogen.master


LOG = logging.getLogger(__name__)
PREFIX = 'ansible.module_utils.'


# Analog of `importlib.machinery.ModuleSpec` or `pkgutil.ModuleInfo`.
#   name    Unqualified name of the module.
#   path    Filesystem path of the module.
#   kind    One of the constants in `imp`, as returned in `imp.find_module()`
#   parent  `ansible_mitogen.module_finder.Module` of parent package (if any).
Module = collections.namedtuple('Module', 'name path kind parent')


def get_fullname(module):
    """
    Reconstruct a Module's canonical path by recursing through its parents.
    """
    bits = [str(module.name)]
    while module.parent:
        bits.append(str(module.parent.name))
        module = module.parent
    return '.'.join(reversed(bits))


def get_code(module):
    """
    Compile and return a Module's code object.
    """
    fp = open(module.path, 'rb')
    try:
        return compile(fp.read(), str(module.name), 'exec')
    finally:
        fp.close()


def is_pkg(module):
    """
    Return :data:`True` if a Module represents a package.
    """
    return module.kind == imp.PKG_DIRECTORY


def find(name, path=(), parent=None):
    """
    Return a Module instance describing the first matching module found on the
    search path.

    :param str name:
        Module name.
    :param list path:
        List of directory names to search for the module.
    :param Module parent:
        Optional module parent.
    """
    assert isinstance(path, tuple)
    head, _, tail = name.partition('.')
    try:
        tup = imp.find_module(head, list(path))
    except ImportError:
        return parent

    fp, modpath, (suffix, mode, kind) = tup
    if fp:
        fp.close()

    if parent and modpath == parent.path:
        # 'from timeout import timeout', where 'timeout' is a function but also
        # the name of the module being imported.
        return None

    if kind == imp.PKG_DIRECTORY:
        modpath = os.path.join(modpath, '__init__.py')

    module = Module(head, modpath, kind, parent)
    # TODO: this code is entirely wrong on Python 3.x, but works well enough
    # for Ansible. We need a new find_child() that only looks in the package
    # directory, never falling back to the parent search path.
    if tail and kind == imp.PKG_DIRECTORY:
        return find_relative(module, tail, path)
    return module


def find_relative(parent, name, path=()):
    if parent.kind == imp.PKG_DIRECTORY:
        path = (os.path.dirname(parent.path),) + path
    return find(name, path, parent=parent)


def scan_fromlist(code):
    """Return an iterator of (level, name) for explicit imports in a code
    object.

    Not all names identify a module. `from os import name, path` generates
    `(0, 'os.name'), (0, 'os.path')`, but `os.name` is usually a string.

    >>> src = 'import a; import b.c; from d.e import f; from g import h, i\\n'
    >>> code = compile(src, '<str>', 'exec')
    >>> list(scan_fromlist(code))
    [(0, 'a'), (0, 'b.c'), (0, 'd.e.f'), (0, 'g.h'), (0, 'g.i')]
    """
    for level, modname_s, fromlist in mitogen.master.scan_code_imports(code):
        for name in fromlist:
            yield level, str('%s.%s' % (modname_s, name))
        if not fromlist:
            yield level, modname_s


def walk_imports(code, prefix=None):
    """Return an iterator of names for implicit parent imports & explicit
    imports in a code object.

    If a prefix is provided, then only children of that prefix are included.
    Not all names identify a module. `from os import name, path` generates
    `'os', 'os.name', 'os.path'`, but `os.name` is usually a string.

    >>> source = 'import a; import b; import b.c; from b.d import e, f\\n'
    >>> code = compile(source, '<str>', 'exec')
    >>> list(walk_imports(code))
    ['a', 'b', 'b', 'b.c', 'b', 'b.d', 'b.d.e', 'b.d.f']
    >>> list(walk_imports(code, prefix='b'))
    ['b.c', 'b.d', 'b.d.e', 'b.d.f']
    """
    if prefix is None:
        prefix = ''
    pattern = re.compile(r'(^|\.)(\w+)')
    start = len(prefix)
    for _, name, fromlist in mitogen.master.scan_code_imports(code):
        if not name.startswith(prefix):
            continue
        for match in pattern.finditer(name, start):
            yield name[:match.end()]
        for leaf in fromlist:
            yield str('%s.%s' % (name, leaf))


def scan(module_name, module_path, search_path):
    # type: (str, str, list[str]) -> list[(str, str, bool)]
    """Return a list of (name, path, is_package) for ansible.module_utils
    imports used by an Ansible module.
    """
    log = LOG.getChild('scan')
    log.debug('%r, %r, %r', module_name, module_path, search_path)

    if sys.version_info >= (3, 4):
        result = _scan_importlib_find_spec(
            module_name, module_path, search_path,
        )
        log.debug('_scan_importlib_find_spec %r', result)
    else:
        result = _scan_imp_find_module(module_name, module_path, search_path)
        log.debug('_scan_imp_find_module %r', result)
    return result


def _scan_importlib_find_spec(module_name, module_path, search_path):
    # type: (str, str, list[str]) -> list[(str, str, bool)]
    module = importlib.machinery.ModuleSpec(
        module_name, loader=None, origin=module_path,
    )
    prefix = importlib.machinery.ModuleSpec(
        PREFIX.rstrip('.'), loader=None,
    )
    prefix.submodule_search_locations = search_path
    queue = collections.deque([module])
    specs = {prefix.name: prefix}
    while queue:
        spec = queue.popleft()
        if spec.origin is None:
            continue
        try:
            with open(spec.origin, 'rb') as f:
                code = compile(f.read(), spec.name, 'exec')
        except Exception as exc:
            raise ValueError((exc, module, spec, specs))

        for name in walk_imports(code, prefix.name):
            if name in specs:
                continue

            parent_name = name.rpartition('.')[0]
            parent = specs[parent_name]
            if parent is None or not parent.submodule_search_locations:
                specs[name] = None
                continue

            child = importlib.util._find_spec(
                name, parent.submodule_search_locations,
            )
            if child is None or child.origin is None:
                specs[name] = None
                continue

            specs[name] = child
            queue.append(child)

    del specs[prefix.name]
    return sorted(
        (spec.name, spec.origin, spec.submodule_search_locations is not None)
        for spec in specs.values() if spec is not None
    )


def _scan_imp_find_module(module_name, module_path, search_path):
    # type: (str, str, list[str]) -> list[(str, str, bool)]
    module = Module(module_name, module_path, imp.PY_SOURCE, None)
    stack = [module]
    seen = set()

    while stack:
        module = stack.pop(0)
        for level, fromname in scan_fromlist(get_code(module)):
            if not fromname.startswith(PREFIX):
                continue

            imported = find(fromname[len(PREFIX):], search_path)
            if imported is None or imported in seen:
                continue

            seen.add(imported)
            stack.append(imported)
            parent = imported.parent
            while parent:
                fullname = get_fullname(parent)
                module = Module(fullname, parent.path, parent.kind, None)
                if module not in seen:
                    seen.add(module)
                    stack.append(module)
                parent = parent.parent

    return sorted(
        (PREFIX + get_fullname(module), module.path, is_pkg(module))
        for module in seen
    )
