"""
Measure latency of local RPC.
"""

import mitogen.core
import mitogen.utils
import ansible_mitogen.affinity

mitogen.utils.setup_gil()
ansible_mitogen.affinity.policy.assign_worker()

try:
    xrange
except NameError:
    xrange = range

def do_nothing():
    pass

@mitogen.main()
def main(router):
    f = router.fork()
    f.call(do_nothing)
    t0 = mitogen.core.now()
    for x in xrange(20000):
        f.call(do_nothing)
    print('++', int(1e6 * ((mitogen.core.now() - t0) / (1.0+x))), 'usec')
