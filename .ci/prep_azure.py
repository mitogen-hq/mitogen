#!/usr/bin/env python

import os
import sys

import ci_lib

batches = []

if 0 and os.uname()[0] == 'Linux':
    batches += [
        [
            "sudo chown `whoami`: ~",
            "chmod u=rwx,g=rx,o= ~",

            "sudo mkdir /var/run/sshd",
            "sudo /etc/init.d/ssh start",

            "mkdir -p ~/.ssh",
            "chmod u=rwx,go= ~/.ssh",

            "ssh-keyscan -H localhost >> ~/.ssh/known_hosts",
            "chmod u=rw,go= ~/.ssh/known_hosts",

            "cat tests/data/docker/mitogen__has_sudo_pubkey.key > ~/.ssh/id_rsa",
            "chmod u=rw,go= ~/.ssh/id_rsa",

            "cat tests/data/docker/mitogen__has_sudo_pubkey.key.pub > ~/.ssh/authorized_keys",
            "chmod u=rw,go=r ~/.ssh/authorized_keys",
        ]
    ]

if ci_lib.have_apt():
    batches.append([
        'echo force-unsafe-io | sudo tee /etc/dpkg/dpkg.cfg.d/nosync',
        'sudo add-apt-repository ppa:deadsnakes/ppa',
        'sudo apt-get update',
        'sudo apt-get -y install '
            'python{pv} '
            'python{pv}-dev '
            'libsasl2-dev '
            'libldap2-dev '
            .format(pv=os.environ['PYTHONVERSION'])
    ])


if ci_lib.have_docker():
    batches.extend(
        ['docker pull %s' % (ci_lib.image_for_distro(distro),)]
        for distro in ci_lib.DISTROS
    )


ci_lib.run_batches(batches)
