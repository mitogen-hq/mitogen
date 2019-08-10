"""
Measure latency of .fork() setup/teardown.
"""

import mitogen
import mitogen.core

@mitogen.main()
def main(router):
    t0 = mitogen.core.now()
    for x in xrange(200):
        t = mitogen.core.now()
        ctx = router.fork()
        ctx.shutdown(wait=True)
    print '++', 1000 * ((mitogen.core.now() - t0) / (1.0+x))
