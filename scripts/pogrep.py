
# issue #429: tool for extracting keys out of message catalogs and turning them
# into the big gob of base64 as used in mitogen/sudo.py
#
# Usage:
#   - apt-get source libpam0g
#   - cd */po/
#   - python ~/pogrep.py "Password: "
from __future__ import print_function

import sys
import shlex
import glob


last_word = None

for path in glob.glob('*.po'):
    for line in open(path):
        bits = shlex.split(line, comments=True)
        if not bits:
            continue

        word = bits[0]
        if len(bits) < 2 or not word:
            continue

        rest = bits[1]
        if not rest:
            continue

        if last_word == 'msgid' and word == 'msgstr':
            if last_rest == sys.argv[1]:
                thing = rest.rstrip(': ').decode('utf-8').lower().encode('utf-8').encode('base64').rstrip()
                print('    %-60s # %s' % (repr(thing)+',', path))

        last_word = word
        last_rest = rest

#ag -A 1 'msgid "Password: "'|less | grep msgstr | grep -v '""'|cut -d'"' -f2|cut -d'"' -f1| tr -d :

