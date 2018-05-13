
from __future__ import absolute_import
import collections
import imp
import os
import sys

import mitogen.master
import ansible.module_utils


PREFIX = 'ansible.module_utils.'


Module = collections.namedtuple('Module', 'name path kind parent')


def get_fullname(module):
    bits = [str(module.name)]
    while module.parent:
        bits.append(str(module.parent.name))
        module = module.parent
    return '.'.join(reversed(bits))


def get_code(module):
    fp = open(module.path)
    try:
        return compile(fp.read(), str(module.name), 'exec')
    finally:
        fp.close()


def is_pkg(module):
    return module.kind == imp.PKG_DIRECTORY


def find(name, path=(), parent=None):
    """
    (Name, search path) -> Module instance or None.
    """
    head, _, tail = name.partition('.')
    try:
        tup = imp.find_module(head, list(path))
    except ImportError:
        return parent

    fp, path, (suffix, mode, kind) = tup
    if fp:
        fp.close()

    if kind == imp.PKG_DIRECTORY:
        path = os.path.join(path, '__init__.py')
    module = Module(head, path, kind, parent)
    if tail:
        return find_relative(module, tail, path)
    return module


def find_relative(parent, name, path=()):
    path = [os.path.dirname(parent.path)] + list(path)
    return find(name, path, parent=parent)


def scan_fromlist(code):
    for level, modname_s, fromlist in mitogen.master.scan_code_imports(code):
        for name in fromlist:
            yield level, '%s.%s' % (modname_s, name)
        if not fromlist:
            yield level, modname_s


def scan(module_name, module_path, search_path):
    module = Module(
        name=module_name,
        path=module_path,
        kind=imp.PY_SOURCE,
        parent=None,
    )
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

            if imported in seen:
                continue

            seen.add(imported)
            stack.append(imported)
            parent = imported.parent
            while parent:
                module = Module(
                    name=get_fullname(parent),
                    path=parent.path,
                    kind=parent.kind,
                    parent=None,
                )
                if module not in seen:
                    seen.add(module)
                    stack.append(module)
                parent = parent.parent

    return sorted(
        (PREFIX + get_fullname(module), module.path, is_pkg(module))
        for module in seen
    )
