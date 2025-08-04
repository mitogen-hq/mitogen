import fcntl
import os
import sys


def shout_stdout(size):
    sys.stdout.write('A' * size)
    return 'success'


def file_is_blocking(fobj):
    return not (fcntl.fcntl(fobj.fileno(), fcntl.F_GETFL) & os.O_NONBLOCK)


def stdio_is_blocking():
    return [file_is_blocking(f) for f in [sys.stdin, sys.stdout, sys.stderr]]
