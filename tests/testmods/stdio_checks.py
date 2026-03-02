import fcntl
import os
import sys


def _shout_stdout_py3(size):
    nwritten = sys.stdout.write('A' * size)
    return nwritten


def _shout_stdout_py2(size):
    shout = 'A' * size
    nwritten = 0
    while nwritten < size:
        nwritten += os.write(sys.stdout.fileno(), shout[-nwritten:])
    return nwritten


def shout_stdout(size):
    if sys.version_info > (3, 0):
        return _shout_stdout_py3(size)
    else:
        return _shout_stdout_py2(size)


def file_is_blocking(fobj):
    return not (fcntl.fcntl(fobj.fileno(), fcntl.F_GETFL) & os.O_NONBLOCK)


def stdio_is_blocking():
    return [file_is_blocking(f) for f in [sys.stdin, sys.stdout, sys.stderr]]
