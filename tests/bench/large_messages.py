# Verify _receive_one() quadratic behaviour fixed.

import mitogen
import mitogen.core


@mitogen.main()
def main(router):
    c = router.fork()

    n = 1048576 * 127
    s = ' ' * n
    print('bytes in %.2fMiB string...' % (n/1048576.0),)

    t0 = mitogen.core.now()
    for x in range(10):
        tt0 = mitogen.core.now()
        assert n == c.call(len, s)
        print('took %dms' % (1000 * (mitogen.core.now() - tt0),))
    t1 = mitogen.core.now()
    print('total %dms / %dms avg / %.2fMiB/sec' % (
        1000 * (t1 - t0),
        (1000 * (t1 - t0)) / (x + 1),
        ((n * (x + 1)) / (t1 - t0)) / 1048576.0,
    ))
