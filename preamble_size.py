"""
Print the size of a typical SSH command line and the bootstrap code sent to new
contexts.
"""

import inspect
import zlib

import econtext.master
import econtext.ssh

context = econtext.master.Context(None, name='default', hostname='default')
stream = econtext.ssh.Stream(context)
print 'SSH command size: %s' % (len(' '.join(stream.get_boot_command())),)
print 'Preamble size: %s (%.2fKiB)' % (
    len(stream.get_preamble()),
    len(stream.get_preamble()) / 1024.0,
)

master = len(zlib.compress(econtext.master.minimize_source(inspect.getsource(econtext.master))))
print 'econtext.master size: %s (%.2fKiB)' % (master, master / 1024.0)
