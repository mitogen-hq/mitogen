#!/usr/bin/env python
# Run tests/ansible/all.yml under Ansible and Ansible-Mitogen

import collections
import glob
import os
import signal
import sys

import jinja2

import ci_lib


TMP = ci_lib.TempDir(prefix='mitogen_ci_ansible')
TMP_HOSTS_DIR = os.path.join(TMP.path, 'hosts')


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
    containers = ci_lib.container_specs(ci_lib.DISTRO_SPECS.split())
    ci_lib.start_containers(containers)


with ci_lib.Fold('job_setup'):
    os.chmod(ci_lib.TESTS_SSH_PRIVATE_KEY_FILE, int('0600', 8))
    os.chdir(ci_lib.ANSIBLE_TESTS_DIR)

    os.mkdir(TMP_HOSTS_DIR)
    for path in glob.glob(os.path.join(ci_lib.ANSIBLE_TESTS_HOSTS_DIR, '*')):
        if not path.endswith('default.hosts'):
            os.symlink(path, os.path.join(TMP_HOSTS_DIR, os.path.basename(path)))

    distros = collections.defaultdict(list)
    families = collections.defaultdict(list)
    for container in containers:
        distros[container['distro']].append(container['name'])
        families[container['family']].append(container['name'])

    jinja_env = jinja2.Environment(
        loader=jinja2.FileSystemLoader(
            searchpath=ci_lib.ANSIBLE_TESTS_TEMPLATES_DIR,
        ),
        lstrip_blocks=True,  # Remove spaces and tabs from before a block
        trim_blocks=True,  # Remove first newline after a block
    )
    inventory_template = jinja_env.get_template('test-targets.j2')
    inventory_path = os.path.join(TMP_HOSTS_DIR, 'test-targets.ini')

    with open(inventory_path, 'w') as fp:
        fp.write(inventory_template.render(
            containers=containers,
            distros=distros,
            families=families,
        ))

    ci_lib.dump_file(inventory_path)

with ci_lib.Fold('ansible'):
    playbook = os.environ.get('PLAYBOOK', 'all.yml')
    try:
        ci_lib.run('python -b ./run_ansible_playbook.py %s -i "%s" %s',
            playbook, TMP_HOSTS_DIR, ' '.join(sys.argv[1:]),
        )
    except:
        pause_if_interactive()
        raise


ci_lib.check_stray_processes(interesting, containers)

pause_if_interactive()
