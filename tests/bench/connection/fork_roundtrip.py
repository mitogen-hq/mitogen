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
    import optparse
    parser = optparse.OptionParser(description=__doc__)
    parser.add_option(
        '-i', '--iterations', type=int, metavar='N', default=20000,
        help='Number of iterations (default %default)')
    parser.add_option('--debug', action='store_true')
    opts, args = parser.parse_args()

    f = router.fork(debug=opts.debug)
    f.call(do_nothing)
    t0 = mitogen.core.now()
    for x in xrange(opts.iterations):
        f.call(do_nothing)
    print('++', int(1e6 * ((mitogen.core.now() - t0) / (1.0+x))), 'usec')
