import sys

if sys.version_info >= (2, 6):
    from mitogen.imports._ast import scan_imports
else:
    from mitogen.imports._dis import scan_imports
