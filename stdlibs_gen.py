import pathlib

import stdlibs

VERSIONS_2x = [
    (2, 4),
    (2, 5),
    (2, 6),
    (2, 7),
]

VERSIONS_3x = [
    (3, 6),
    (3, 7),
    (3, 8), 
    (3, 9),
]

VERSIONS = VERSIONS_2x + VERSIONS_3x

STDLIBS = {
    version: sorted(stdlibs.stdlib_module_names('%d.%d' % version))
    for version in VERSIONS
}

pathlib.Path('mitogen/imports/stdlibs').mkdir(parents=True, exist_ok=True)
for version, names in STDLIBS.items():
    with open('mitogen/imports/stdlibs/py%d%d.py' % version, 'w', encoding='utf-8') as f:
        f.write('module_names = frozenset([\n')
        f.write(''.join("    '%s',\n" % name for name in names))
        f.write('])\n')
