"""
Measure latency of .local() setup.
"""

import mitogen
import mitogen.core
import mitogen.utils
import ansible_mitogen.affinity


mitogen.utils.setup_gil()
#ansible_mitogen.affinity.policy.assign_worker()


@mitogen.main()
def main(router):
    t0 = mitogen.core.now()
    for x in range(100):
        t = mitogen.core.now()
        f = router.local()# debug=True)
        tt = mitogen.core.now()
        print(x, 1000 * (tt - t))
    print('%.03f ms' % (1000 * (mitogen.core.now() - t0) / (1.0 + x)))
