import sys


if True:
    import in_if_always_true
    from in_if_always_true import x as y, z
else:
    import in_else_never_true
    from in_else_never_true import x as y, z

if sys.version >= (3, 0):
    import in_if_py3
    from in_if_py3 import x as y, z
else:
    import in_else_py2
    from in_else_py2 import x as y, z
