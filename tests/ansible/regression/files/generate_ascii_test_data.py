'''
Write lines of deterministic ASCII test data

```console
$ python generate_ascii_test_data.py 192
000000000000000000 mitogen-test-file ABCDEFGHIJKLMNOPQRSTUVWXYZ
000000000000000064 mitogen-test-file BCDEFGHIJKLMNOPQRSTUVWXYZA
000000000000000128 mitogen-test-file CDEFGHIJKLMNOPQRSTUVWXYZAB
```
'''

import os
import sys

if sys.version_info < (3, 0):
    range = xrange  # noqa: F821

# Padding added to make each line LINE_SIZE bytes long, including a newline.
# PADDING_POOL is repeated to eliminate repeated concatenations in the loop.
PADDING_TEXT = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ'.encode('ascii')
PADDING_SIZE = 26
PADDING_POOL = PADDING_TEXT * 2

LINE_TMPL = '%%018d mitogen-test-file %%.%ds\n'.encode('ascii') % PADDING_SIZE
LINE_SIZE = 64

def format_line(lineno):
    # type: (int) -> bytes
    line_offset = lineno * LINE_SIZE
    padding_shift = lineno % PADDING_SIZE
    return LINE_TMPL % (line_offset, PADDING_POOL[padding_shift:])


def main():
    assert len(PADDING_POOL) >= 2 * PADDING_SIZE
    assert len(format_line(0)) == LINE_SIZE

    try:
        output_size = int(sys.argv[1])
        if output_size < 0 or output_size % LINE_SIZE != 0:
            raise ValueError
    except IndexError:
        prog = os.path.basename(sys.argv[0])
        raise SystemExit('Usage: %s output_size [output_file]' % prog)
    except ValueError:
        raise SystemExit(
            'Error: output_size must be >= 0 and a multiple of line size (%d), '
            'got: %s' % (LINE_SIZE, sys.argv[1])
        )

    if len(sys.argv) >= 3 and sys.argv[2] != '-':
        output_file = open(sys.argv[2], 'wb')
    else:
        output_file = os.fdopen(sys.stdout.fileno(), 'wb')

    with output_file as f:
        for lineno in range(0, output_size // LINE_SIZE):
            line = format_line(lineno)
            f.write(line)

    raise SystemExit


if __name__ == '__main__':
    main()
