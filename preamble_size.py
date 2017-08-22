"""
Print the size of a typical SSH command line and the bootstrap code sent to new
contexts.
"""

import inspect
import zlib

import econtext.master
import econtext.ssh
import econtext.sudo

with econtext.master.Broker() as broker:
    router = econtext.core.Router(broker)
    context = econtext.master.Context(router, 0)
    stream = econtext.ssh.Stream(router, 0, context.key, hostname='foo')
    print 'SSH command size: %s' % (len(' '.join(stream.get_boot_command())),)
    print 'Preamble size: %s (%.2fKiB)' % (
        len(stream.get_preamble()),
        len(stream.get_preamble()) / 1024.0,
    )

for mod in (
        econtext.master,
        econtext.ssh,
        econtext.sudo,
        ):
    sz = len(zlib.compress(econtext.master.minimize_source(inspect.getsource(mod))))
    print '%s size: %s (%.2fKiB)' % (mod.__name__, sz, sz / 1024.0)
