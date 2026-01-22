'Measure throughput of messages.'

import mitogen
import mitogen.core


@mitogen.main()
def main(router):
    import optparse
    parser = optparse.OptionParser(description=__doc__)
    parser.add_option(
        '-i', '--iterations', type=int, metavar='N', default=10,
        help='Number of iterations (default %default)')
    parser.add_option('--debug', action='store_true')
    opts, args = parser.parse_args()

    c = router.fork(debug=opts.debug)

    n = 1048576 * 127
    s = ' ' * n

    t0 = mitogen.core.now()
    for x in mitogen.core.range(opts.iterations):
        tt0 = mitogen.core.now()
        assert n == c.call(len, s)

    t1 = mitogen.core.now()
    mean = (t1 - t0) / opts.iterations
    transferred_size = n * opts.iterations
    transfer_rate = transferred_size / (t1 - t0)
    print('++ iterations %d, mean %.03f ms, rate %.03f MiB/s'
          % (opts.iterations, 1e3 * mean, transfer_rate / 2**20))
