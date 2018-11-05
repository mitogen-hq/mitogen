#!/usr/bin/env python
# Run preparation steps in parallel.

import subprocess
import ci_lib

subprocess.check_call(
    'echo force-unsafe-io | sudo tee /etc/dpkg/dpkg.cfg.d/nosync',
    shell=True,
)

procs = [
    subprocess.Popen(
        'pip install -r dev_requirements.txt 2>&1 | cat',
        shell=True,
    ),
    subprocess.Popen(
        """
        sudo add-apt-repository ppa:deadsnakes/ppa && \
        ( sudo apt-get update 2>&1 | cat ) && \
        sudo apt-get -y install \
            python2.6 python2.6-dev libsasl2-dev libldap2-dev 2>&1 | cat
        """,
        shell=True,
    )
]

procs += [
    subprocess.Popen(
        'docker pull mitogen/%s-test 2>&1 | cat' % (distro,),
        shell=True
    )
    for distro in ci_lib.DISTROS
]

assert [proc.wait() for proc in procs] == [0] * len(procs)
