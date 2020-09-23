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

# @dw: The VSTS-shipped Pythons available via UsePythonVErsion are pure garbage,
# broken symlinks, incorrect permissions and missing codecs. So we use the
# deadsnakes PPA to get sane Pythons, and setup a virtualenv to install our
# stuff into. The virtualenv can probably be removed again, but this was a
# hard-fought battle and for now I am tired of this crap.
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
            .format(pv=os.environ['PYTHONVERSION']),
        'sudo ln -fs /usr/bin/python{pv} /usr/local/bin/python{pv}'
        .format(pv=os.environ['PYTHONVERSION'])
    ])


# Mac's System Integrity Protection prevents symlinking /usr/bin
# and Azure isn't allowing disabling it apparently: https://developercommunityapi.westus.cloudapp.azure.com/idea/558702/allow-disabling-sip-on-microsoft-hosted-macos-agen.html
# so we'll use /usr/local/bin/python for everything
if ci_lib.have_brew():
    batches.append([
        'brew install python@{pv}'
        .format(pv=os.environ['PYTHONVERSION'])
    ])

# setup venv
# need wheel before building virtualenv because of bdist_wheel and setuptools deps
venv_steps = ['/usr/local/bin/python{pv} -m pip install -U pip wheel setuptools'.format(pv=os.environ['PYTHONVERSION'])]
if os.environ['PYTHONVERSION'].startswith('2'):
    venv_steps.extend([
        '/usr/local/bin/python{pv} -m pip install -U virtualenv'.format(pv=os.environ['PYTHONVERSION']),
        '/usr/local/bin/python{pv} -m virtualenv /tmp/venv -p /usr/local/bin/python{pv}'.format(pv=os.environ['PYTHONVERSION'])
    ])
else:
    venv_steps.append('/usr/local/bin/python{pv} -m venv /tmp/venv'.format(pv=os.environ['PYTHONVERSION']))
batches.append(venv_steps)


if ci_lib.have_docker():
    batches.extend(
        ['docker pull %s' % (ci_lib.image_for_distro(distro),)]
        for distro in ci_lib.DISTROS
    )


ci_lib.run_batches(batches)
