
from __future__ import absolute_import
import imp
import os
import sys

import mitogen.master
import ansible.module_utils


PREFIX = 'ansible.module_utils.'


class Module(object):
    def __init__(self, name, path, kind=imp.PY_SOURCE, parent=None):
        self.name = name
        self.path = path
        self.kind = kind
        self.is_pkg = kind == imp.PKG_DIRECTORY
        self.parent = parent

    def __hash__(self):
        return hash(self.path)

    def __eq__(self, other):
        return self.path == other.path

    def fullname(self):
        bits = [str(self.name)]
        while self.parent:
            bits.append(str(self.parent.name))
            self = self.parent
        return '.'.join(reversed(bits))

    def code(self):
        fp = open(self.path)
        try:
            return compile(fp.read(), str(self.name), 'exec')
        finally:
            fp.close()


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
    module = Module(module_name, module_path)
    stack = [module]
    seen = set()

    while stack:
        module = stack.pop(0)
        for level, fromname in scan_fromlist(module.code()):
            if not fromname.startswith(PREFIX):
                continue

            imported = find(fromname[len(PREFIX):], search_path)
            if imported is None or imported in seen:
                continue

            seen.add(imported)
            parent = imported.parent
            while parent:
                module = Module(name=parent.fullname(), path=parent.path,
                                kind=parent.kind)
                if module not in seen:
                    seen.add(module)
                    stack.append(module)
                parent = parent.parent

    return sorted(
        (PREFIX + module.fullname(), module.path, module.is_pkg)
        for module in seen
    )
