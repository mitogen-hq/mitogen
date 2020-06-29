#!/usr/bin/env python
# Run tests/ansible/all.yml under Ansible and Ansible-Mitogen

import glob
import os
import signal
import sys

import ci_lib
from ci_lib import run


TESTS_DIR = os.path.join(ci_lib.GIT_ROOT, 'tests/ansible')
HOSTS_DIR = os.path.join(ci_lib.TMP, 'hosts')


def pause_if_interactive():
    if os.path.exists('/tmp/interactive'):
        while True:
            signal.pause()


interesting = ci_lib.get_interesting_procs()


with ci_lib.Fold('unit_tests'):
    os.environ['SKIP_MITOGEN'] = '1'
    ci_lib.run('./run_tests -v')


ci_lib.check_stray_processes(interesting)


with ci_lib.Fold('docker_setup'):
    containers = ci_lib.make_containers()
    ci_lib.start_containers(containers)


with ci_lib.Fold('job_setup'):
    # Don't set -U as that will upgrade Paramiko to a non-2.6 compatible version.
    run("pip install -q ansible==%s", ci_lib.ANSIBLE_VERSION)

    os.chdir(TESTS_DIR)
    os.chmod('../data/docker/mitogen__has_sudo_pubkey.key', int('0600', 7))

    run("mkdir %s", HOSTS_DIR)
    for path in glob.glob(TESTS_DIR + '/hosts/*'):
        if not path.endswith('default.hosts'):
            run("ln -s %s %s", path, HOSTS_DIR)

    inventory_path = os.path.join(HOSTS_DIR, 'target')
    with open(inventory_path, 'w') as fp:
        fp.write('[test-targets]\n')
        fp.writelines(
            "%(name)s "
            "ansible_host=%(hostname)s "
            "ansible_port=%(port)s "
            "ansible_python_interpreter=%(python_path)s "
            "ansible_user=mitogen__has_sudo_nopw "
            "ansible_password=has_sudo_nopw_password"
            "\n"
            % container
            for container in containers
        )

    ci_lib.dump_file(inventory_path)

    if not ci_lib.exists_in_path('sshpass'):
        run("sudo apt-get update")
        run("sudo apt-get install -y sshpass")

    run("bash -c 'sudo ln -vfs /usr/lib/python2.7/plat-x86_64-linux-gnu/_sysconfigdata_nd.py /usr/lib/python2.7 || true'")
    run("bash -c 'sudo ln -vfs /usr/lib/python2.7/plat-x86_64-linux-gnu/_sysconfigdata_nd.py $VIRTUAL_ENV/lib/python2.7 || true'")

with ci_lib.Fold('ansible'):
    playbook = os.environ.get('PLAYBOOK', 'all.yml')
    try:
        run('./run_ansible_playbook.py %s -i "%s" %s',
            playbook, HOSTS_DIR, ' '.join(sys.argv[1:]))
    except:
        pause_if_interactive()
        raise


ci_lib.check_stray_processes(interesting, containers)

pause_if_interactive()
