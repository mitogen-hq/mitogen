
import imp
import os
import sys
import mitogen.master


class Name(object):
    def __str__(self):
        return self.identifier

    def __repr__(self):
        return 'Name(%r)' % (self.identifier,)

    def __init__(self, identifier):
        self.identifier = identifier

    def head(self):
        head, _, tail = self.identifier.partition('.')
        return head

    def tail(self):
        head, _, tail = self.identifier.partition('.')
        return tail

    def pop_n(self, level):
        name = self.identifier
        for _ in xrange(level):
            if '.' not in name:
                return None
            name, _, _ = self.identifier.rpartition('.')
        return Name(name)

    def append(self, part):
        return Name('%s.%s' % (self.identifier, part))


class Module(object):
    def __init__(self, name, path, kind=imp.PY_SOURCE, parent=None):
        self.name = Name(name)
        self.path = path
        if kind == imp.PKG_DIRECTORY:
            self.path = os.path.join(self.path, '__init__.py')
        self.kind = kind
        self.parent = parent

    def fullname(self):
        bits = [str(self.name)]
        while self.parent:
            bits.append(str(self.parent.name))
            self = self.parent
        return '.'.join(reversed(bits))

    def __repr__(self):
        return 'Module(%r, path=%r, parent=%r)' % (
            self.name,
            self.path,
            self.parent,
        )

    def dirname(self):
        return os.path.dirname(self.path)

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
    try:
        tup = imp.find_module(name.head(), list(path))
    except ImportError:
        return parent

    fp, path, (suffix, mode, kind) = tup
    if fp:
        fp.close()

    module = Module(name.head(), path, kind, parent)
    if name.tail():
        return find_relative(module, Name(name.tail()), path)
    return module


def find_relative(parent, name, path=()):
    path = [parent.dirname()] + list(path)
    return find(name, path, parent=parent)


def path_pop(s, n):
    return os.pathsep.join(s.split(os.pathsep)[-n:])


def scan(module, path):
    scanner = mitogen.master.scan_code_imports(module.code())
    for level, modname_s, fromlist in scanner:
        modname = Name(modname_s)
        if level == -1:
            imported = find_relative(module, modname, path)
        elif level:
            subpath = [path_pop(module.dirname(), level)] + list(path)
            imported = find(modname.pop_n(level), subpath)
        else:
            imported = find(modname.pop_n(level), path)

        if imported and mitogen.master.is_stdlib_path(imported.path):
            continue

        if imported and fromlist:
            have = False
            for fromname_s in fromlist:
                fromname = modname.append(fromname_s)
                f_imported = find_relative(imported, fromname, path)
                if f_imported and f_imported.fullname() == fromname.identifier:
                    have = True
                    yield fromname, f_imported, None
            if have:
                continue

        if imported:
            yield modname, imported


module = Module(name='ansible_module_apt', path='/Users/dmw/src/mitogen/.venv/lib/python2.7/site-packages/ansible/modules/packaging/os/apt.py')
path = tuple(sys.path)
path = ('/Users/dmw/src/ansible/lib',) + path


from pprint import pprint
for name, imported in scan(module, sys.path):
    print '%s: %s' % (name, imported and (str(name) == imported.fullname()))
