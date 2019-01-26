"""
Measure latency of local RPC.
"""

import time

import mitogen
import mitogen.utils

mitogen.utils.setup_gil()

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
    t0 = time.time()
    for x in xrange(20000):
        f.call(do_nothing)
    print('++', int(1e6 * ((time.time() - t0) / (1.0+x))), 'usec')
