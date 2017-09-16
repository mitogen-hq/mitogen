
import mitogen.utils
import mitogen.fakessh


@mitogen.utils.run_with_router
def main(router):
    import logging
    mitogen.utils.log_to_file(level=logging.INFO)
    router.enable_debug()
    #mitogen.fakessh.run_with_fake_ssh(router, ['bash', '-c', 'echo $PATH'])
    #mitogen.fakessh.run_with_fake_ssh(router, ['bash', '-c', 'ls -Gl $SSH_PATH'])
    # k3 = router.ssh(hostname='k3')
    k3 = router.local()
    print 'GOT HERE'
    import os
    k3.call(os.system, 'hostname')
    return
    #sud = router.sudo(via=k3, username='root')
    sud = k3

    mitogen.fakessh.run_with_fake_ssh(sud, router, ['rsync', '--progress', '-vvvr', 'h:/var/lib/docker'])
    #mitogen.fakessh.run_with_fake_ssh(router, ['bash', '-c', 'ssh h rsync --server . foo'])
    # mitogen.fakessh.run_with_fake_ssh(router, ['bash', '-c', 'ssh k3.botanicus.net -t screen -dr'])
    print 'end of t.py'


import logging
import mitogen.utils
import mitogen.fakessh

@mitogen.utils.run_with_router
def main(router):
    mitogen.utils.log_to_file(level=logging.DEBUG)
    #router.enable_debug()
    #router.enable_debug()

    k3 = router.ssh(hostname='k3')
    sudo = router.sudo(via=k3, username='root')

    mitogen.fakessh.run(sudo, router, ['rsync', '--progress', '-r', 'h:/var/lib/docker'])

