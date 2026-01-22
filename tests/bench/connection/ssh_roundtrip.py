"""
Measure latency of SSH RPC.
"""

import getpass

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
        '-p', '--python', metavar='CMD', default='python3',
        help='Remote python path (default %default)')
    parser.add_option(
        '-u', '--user', metavar='S', default=getpass.getuser(),
        help='Remote username (default %default)')
    parser.add_option('--debug', action='store_true')
    opts, args = parser.parse_args()

    f = router.ssh(
        hostname=args[0], python_path=opts.python, username=opts.user,
        debug=opts.debug,
    )
    f.call(do_nothing)
    t0 = mitogen.core.now()
    end = mitogen.core.now() + 5.0
    i = 0
    while mitogen.core.now() < end:
        f.call(do_nothing)
        i += 1
        t1 = mitogen.core.now()

    print('++', float(1e3 * (t1 - t0) / (1.0+i)), 'ms')
