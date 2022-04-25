# Verify throughput over sudo and SSH at various compression levels.

import os
import tempfile

import mitogen
import mitogen.core
import mitogen.service
import ansible_mitogen.affinity


def prepare():
    pass


def transfer(context, path):
    fp = open('/dev/null', 'wb')
    mitogen.service.FileService.get(context, path, fp)
    fp.close()


def fill_with_random(fp, size):
    n = 0
    s = os.urandom(1048576*16)
    while n < size:
        fp.write(s)
        n += len(s)


def run_test(router, fp, s, context):
    fp.seek(0, 2)
    size = fp.tell()
    print('Testing %s...' % (s,))
    context.call(prepare)
    t0 = mitogen.core.now()
    context.call(transfer, router.myself(), fp.name)
    t1 = mitogen.core.now()
    print('%s took %.2f ms to transfer %.2f MiB, %.2f MiB/s' % (
        s, 1000 * (t1 - t0), size / 1048576.0,
        (size / (t1 - t0) / 1048576.0),
    ))


@mitogen.main()
def main(router):
    ansible_mitogen.affinity.policy.assign_muxprocess()

    bigfile = tempfile.NamedTemporaryFile()
    fill_with_random(bigfile, 1048576*512)

    file_service = mitogen.service.FileService(router)
    pool = mitogen.service.Pool(router, ())
    file_service.register(bigfile.name)
    pool.add(file_service)
    try:
        context = router.local()
        run_test(router, bigfile, 'local()', context)
        context.shutdown(wait=True)

        context = router.sudo()
        run_test(router, bigfile, 'sudo()', context)
        context.shutdown(wait=True)

        context = router.ssh(hostname='localhost', compression=False)
        run_test(router, bigfile, 'ssh(compression=False)', context)
        context.shutdown(wait=True)

        context = router.ssh(hostname='localhost', compression=True)
        run_test(router, bigfile, 'ssh(compression=True)', context)
        context.shutdown(wait=True)
    finally:
        pool.stop()
        bigfile.close()

