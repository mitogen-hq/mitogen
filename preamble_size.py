"""
Print the size of a typical SSH command line and the bootstrap code sent to new
contexts.
"""

import inspect
import zlib

import mitogen.master
import mitogen.ssh
import mitogen.sudo

broker = mitogen.master.Broker()

router = mitogen.core.Router(broker)
context = mitogen.master.Context(router, 0)
stream = mitogen.ssh.Stream(router, 0, context.key, hostname='foo')
broker.shutdown()

print 'SSH command size: %s' % (len(' '.join(stream.get_boot_command())),)
print 'Preamble size: %s (%.2fKiB)' % (
    len(stream.get_preamble()),
    len(stream.get_preamble()) / 1024.0,
)

for mod in (
        mitogen.master,
        mitogen.ssh,
        mitogen.sudo,
        ):
    sz = len(zlib.compress(mitogen.master.minimize_source(inspect.getsource(mod))))
    print '%s size: %s (%.2fKiB)' % (mod.__name__, sz, sz / 1024.0)
