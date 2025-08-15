#!/usr/bin/env python
"""
Print the size of a typical SSH command line and the bootstrap code sent to new
contexts.
"""

import inspect
import sys
import zlib

import mitogen.core
import mitogen.fakessh
import mitogen.fork
import mitogen.master
import mitogen.minify
import mitogen.parent
import mitogen.select
import mitogen.service
import mitogen.ssh
import mitogen.sudo


class Table(object):
    HEADERS = (' ', 'Original', 'Minimized', 'Compressed')
    HEAD_FMT = '{:20} {:^15}  {:^19}  {:^19}'
    ROW_FMT =  '%-20s %6i %5.1fKiB  %5i %4.1fKiB %4.1f%%  %5i %4.1fKiB %4.1f%%'

    def header(self):
        return self.HEAD_FMT.format(*self.HEADERS)


router = mitogen.master.Router()
context = mitogen.parent.Context(router, 0)
options = mitogen.ssh.Options(
    hostname='foo',
    max_message_size=0,
    remote_name='alice@host:1234',
)
conn = mitogen.ssh.Connection(options, router)
conn.context = context

print('SSH command size: %s' % (len(' '.join(conn.get_boot_command())),))
print('Preamble (mitogen.core + econtext) size: %s (%.2fKiB)' % (
    len(conn.get_preamble()),
    len(conn.get_preamble()) / 1024.0,
))
print('')

if '--dump' in sys.argv:
    print(zlib.decompress(conn.get_preamble()))
    exit()


table = Table()
print(table.header())
for mod in (
        mitogen.core,
        mitogen.parent,
        mitogen.fork,
        mitogen.ssh,
        mitogen.sudo,
        mitogen.select,
        mitogen.service,
        mitogen.fakessh,
        mitogen.master,
    ):
    original = inspect.getsource(mod)
    original_size = len(original)
    minimized = mitogen.minify.minimize_source(original)
    minimized_size = len(minimized)
    compressed = zlib.compress(minimized.encode(), 9)
    compressed_size = len(compressed)
    print(
        table.ROW_FMT
    % (
        mod.__name__,
        original_size,
        original_size / 1024.0,
        minimized_size,
        minimized_size / 1024.0,
        100 * minimized_size / float(original_size),
        compressed_size,
        compressed_size / 1024.0,
        100 * compressed_size / float(original_size),
    ))
