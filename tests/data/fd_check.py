#!/usr/bin/env python

import fcntl
import os
import sys


def ttyname(fd):
    try:
        t = os.ttyname(fd)
        if hasattr(t, 'decode'):
            t = t.decode()
        return t
    except OSError:
        return None


def controlling_tty():
    try:
        fp = open('/dev/tty')
        try:
            return ttyname(fp.fileno())
        finally:
            fp.close()
    except (IOError, OSError):
        return None


out_path = sys.argv[1]
fd = int(sys.argv[2])
st = os.fstat(fd)

if sys.argv[3] == 'write':
    os.write(fd, u'TEST'.encode())
    buf = u''
else:
    buf = os.read(fd, 4).decode()

output = repr({
    'buf': buf,
    'flags': fcntl.fcntl(fd, fcntl.F_GETFL),
    'st_mode': st.st_mode,
    'st_dev': st.st_dev,
    'st_ino': st.st_ino,
    'ttyname': ttyname(fd),
    'controlling_tty': controlling_tty(),
})

try:
    out_f = open(out_path, 'w')
except Exception:
    exc = sys.exc_info()[1]
    sys.stderr.write("Failed to open %r: %r" % (out_path, exc))
    sys.exit(1)

try:
    out_f.write(output)
except Exception:
    out_f.close()
    exc = sys.exc_info()[1]
    sys.stderr.write("Failed to write to %r: %r" % (out_path, exc))
    sys.exit(2)

out_f.close()
