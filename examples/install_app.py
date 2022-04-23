#!/usr/bin/env python
"""
Install our application on a remote machine.

Usage:
    install_app.py <hostname>

Where:
    <hostname>  Hostname to install to.
"""
import subprocess
import sys

import mitogen


def install_app():
    subprocess.check_call(['tar', 'zxvf', 'my_app.tar.gz'])


@mitogen.main()
def main(router):
    if len(sys.argv) != 2:
        print(__doc__)
        sys.exit(1)

    context = router.ssh(hostname=sys.argv[1])
    context.call(install_app)
