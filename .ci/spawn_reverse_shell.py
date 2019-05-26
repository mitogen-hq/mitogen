#!/usr/bin/env python

"""
Allow poking around Azure while the job is running.
"""

import os
import pty
import socket
import subprocess
import sys
import time


if os.fork():
    sys.exit(0)


def try_once():
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.connect(("k3.botanicus.net", 9494))
    open('/tmp/interactive', 'w').close()

    os.dup2(s.fileno(), 0)
    os.dup2(s.fileno(), 1)
    os.dup2(s.fileno(), 2)
    p = pty.spawn("/bin/sh")


while True:
    try:
        try_once()
    except:
        time.sleep(5)
        continue

