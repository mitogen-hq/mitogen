"""
Measure latency of .fork() setup/teardown.
"""

import mitogen
import mitogen.core

try:
    xrange
except NameError:
    xrange = range


@mitogen.main()
def main(router):
    import optparse
    parser = optparse.OptionParser(description=__doc__)
    parser.add_option(
        '-i', '--iterations', type=int, metavar='N', default=200,
        help='Number of iterations (default %default)')
    parser.add_option('--debug', action='store_true')
    opts, args = parser.parse_args()

    t0 = mitogen.core.now()
    for x in xrange(opts.iterations):
        t = mitogen.core.now()
        ctx = router.fork(debug=opts.debug)
        ctx.shutdown(wait=True)

    t1 = mitogen.core.now()
    mean = (t1 - t0) / opts.iterations
    print('++ iterations %d, mean %.03f ms' % (opts.iterations, 1e3 * mean))
