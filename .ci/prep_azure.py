#!/usr/bin/env python

import ci_lib

batches = []
batches.append([
    'echo force-unsafe-io | sudo tee /etc/dpkg/dpkg.cfg.d/nosync',
    'sudo add-apt-repository ppa:deadsnakes/ppa',
    'sudo apt-get update',
    'sudo apt-get -y install python2.6 python2.6-dev libsasl2-dev libldap2-dev',
])

batches.append([
    'pip install -r dev_requirements.txt',
])

batches.extend(
    ['docker pull mitogen/%s-test' % (distro,)]
    for distro in ci_lib.DISTROS
)

ci_lib.run_batches(batches)
