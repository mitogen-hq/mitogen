from __future__ import absolute_import
import ast
import sys

def scan_imports(source, filename='<str>'):
    "Yield `(level, name, fromnames)` tuples for imports in `source`"
    tree = ast.parse(source, filename)
    return _iter_tree_imports(tree)


def _iter_tree_imports(tree):
    default_level = 0 if sys.version_info >= (3, 0) else -1

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                yield (default_level, alias.name, ())

        elif isinstance(node, ast.ImportFrom):
            module = node.module or ''
            aliases = tuple(alias.name for alias in node.names)
            if (default_level and node.level == 0 and module == '__future__'
                and 'absolute_import' in aliases):
                default_level = 0
            yield (node.level or default_level, module, aliases)
