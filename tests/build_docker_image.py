#!/usr/bin/env python

import commands
import os
import shlex
import subprocess
import tempfile


DOCKERFILE = r"""
FROM debian:stable
RUN apt-get update
RUN \
    apt-get install -y python2.7 openssh-server sudo rsync git && \
    apt-get clean
RUN \
    mkdir /var/run/sshd && \
    echo '%sudo-nopw ALL=(ALL:ALL) NOPASSWD:ALL' > /etc/sudoers.d/001-sudo-nopw && \
    echo i-am-mitogen-test-docker-image > /etc/sentinel && \
    groupadd sudo-nopw && \
    useradd -m has-sudo -G sudo && \
    useradd -m has-sudo-pubkey -G sudo && \
    useradd -m has-sudo-nopw -G sudo-nopw && \
    useradd -m webapp && \
    ( echo 'root:x' | chpasswd; ) && \
    ( echo 'has-sudo:y' | chpasswd; ) && \
    ( echo 'has-sudo-nopw:y' | chpasswd; ) && \
    mkdir ~has-sudo-pubkey/.ssh

COPY data/docker/has-sudo-pubkey.key.pub /home/has-sudo-pubkey/.ssh/authorized_keys
RUN \
    chown -R has-sudo-pubkey ~has-sudo-pubkey && \
    chmod -R go= ~has-sudo-pubkey

RUN sed -i 's/PermitRootLogin prohibit-password/PermitRootLogin yes/' /etc/ssh/sshd_config
RUN sed 's@session\s*required\s*pam_loginuid.so@session optional pam_loginuid.so@g' -i /etc/pam.d/sshd

ENV NOTVISIBLE "in users profile"
RUN echo "export VISIBLE=now" >> /etc/profile

EXPOSE 22
CMD ["/usr/sbin/sshd", "-D"]

RUN apt-get install -y strace && apt-get clean && { echo '#!/bin/bash\nexec strace -ff -o /tmp/pywrap$$.trace python2.7 "$@"' > /usr/local/bin/pywrap; chmod +x /usr/local/bin/pywrap; }
"""


def sh(s, *args):
    if args:
        s %= tuple(map(commands.mkarg, args))
    return shlex.split(s)


mydir = os.path.abspath(os.path.dirname(__file__))
with tempfile.NamedTemporaryFile(dir=mydir) as dockerfile_fp:
    dockerfile_fp.write(DOCKERFILE)
    dockerfile_fp.flush()

    subprocess.check_call(sh('docker build %s -t d2mw/mitogen-test -f %s',
        mydir,
        dockerfile_fp.name
    ))
