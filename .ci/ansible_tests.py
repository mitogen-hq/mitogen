#!/usr/bin/env python
# Run tests/ansible/all.yml under Ansible and Ansible-Mitogen

import collections
import glob
import os
import signal
import sys

import jinja2

import ci_lib


TEMPLATES_DIR = os.path.join(ci_lib.GIT_ROOT, 'tests/ansible/templates')
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
    containers = ci_lib.container_specs(ci_lib.DISTROS)
    ci_lib.start_containers(containers)


with ci_lib.Fold('job_setup'):
    os.chdir(TESTS_DIR)
    os.chmod('../data/docker/mitogen__has_sudo_pubkey.key', int('0600', 7))

    ci_lib.run("mkdir %s", HOSTS_DIR)
    for path in glob.glob(TESTS_DIR + '/hosts/*'):
        if not path.endswith('default.hosts'):
            ci_lib.run("ln -s %s %s", path, HOSTS_DIR)

    distros = collections.defaultdict(list)
    families = collections.defaultdict(list)
    for container in containers:
        distros[container['distro']].append(container['name'])
        families[container['family']].append(container['name'])

    jinja_env = jinja2.Environment(
        loader=jinja2.FileSystemLoader(searchpath=TEMPLATES_DIR),
        lstrip_blocks=True,  # Remove spaces and tabs from before a block
        trim_blocks=True,  # Remove first newline after a block
    )
    inventory_template = jinja_env.get_template('test-targets.j2')
    inventory_path = os.path.join(HOSTS_DIR, 'target')

    with open(inventory_path, 'w') as fp:
        fp.write(inventory_template.render(
            containers=containers,
            distros=distros,
            families=families,
        ))

    ci_lib.dump_file(inventory_path)

    if not ci_lib.exists_in_path('sshpass'):
        ci_lib.run("sudo apt-get update")
        ci_lib.run("sudo apt-get install -y sshpass")


with ci_lib.Fold('ansible'):
    playbook = os.environ.get('PLAYBOOK', 'all.yml')
    try:
        ci_lib.run('./run_ansible_playbook.py %s -i "%s" %s',
            playbook, HOSTS_DIR, ' '.join(sys.argv[1:]))
    except:
        pause_if_interactive()
        raise


ci_lib.check_stray_processes(interesting, containers)

pause_if_interactive()
