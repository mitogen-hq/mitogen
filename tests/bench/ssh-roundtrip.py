"""
Measure latency of SSH RPC.
"""

import sys

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
    f = router.ssh(hostname=sys.argv[1])
    f.call(do_nothing)
    t0 = mitogen.core.now()
    end = mitogen.core.now() + 5.0
    i = 0
    while mitogen.core.now() < end:
        f.call(do_nothing)
        i += 1
        t1 = mitogen.core.now()

    print('++', float(1e3 * (t1 - t0) / (1.0+i)), 'ms')
