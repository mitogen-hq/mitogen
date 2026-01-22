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
    import optparse
    parser = optparse.OptionParser(description=__doc__)
    parser.add_option(
        '-i', '--iterations', type=int, metavar='N', default=100,
        help='Number of iterations (default %default)')
    parser.add_option('--debug', action='store_true')
    opts, args = parser.parse_args()

    t0 = mitogen.core.now()
    for x in mitogen.core.range(opts.iterations):
        t = mitogen.core.now()
        f = router.local(debug=opts.debug)
        tt = mitogen.core.now()

    t1 = mitogen.core.now()
    mean = (t1 - t0) / opts.iterations
    print('++ iterations %d, mean %.03f ms' % (opts.iterations, 1e3 * mean))
