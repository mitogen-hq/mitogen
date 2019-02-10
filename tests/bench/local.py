"""
Measure latency of .local() setup.
"""

import time

import mitogen
import mitogen.utils
import ansible_mitogen.affinity


mitogen.utils.setup_gil()
#ansible_mitogen.affinity.policy.assign_worker()


@mitogen.main()
def main(router):
    t0=time.time()
    for x in range(100):
        t = time.time()
        f = router.local()# debug=True)
        tt = time.time()
        print(x, 1000 * (tt - t))
    print('%.03f ms' % (1000 * (time.time() - t0) / (1.0 + x)))
