# Copyright 2017, David Wilson
#
# Redistribution and use in source and binary forms, with or without
# modification, are permitted provided that the following conditions are met:
#
# 1. Redistributions of source code must retain the above copyright notice,
# this list of conditions and the following disclaimer.
#
# 2. Redistributions in binary form must reproduce the above copyright notice,
# this list of conditions and the following disclaimer in the documentation
# and/or other materials provided with the distribution.
#
# 3. Neither the name of the copyright holder nor the names of its contributors
# may be used to endorse or promote products derived from this software without
# specific prior written permission.
#
# THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS"
# AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE
# IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE
# ARE DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT HOLDER OR CONTRIBUTORS BE
# LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR
# CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF
# SUBSTITUTE GOODS OR SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS
# INTERRUPTION) HOWEVER CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN
# CONTRACT, STRICT LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE)
# ARISING IN ANY WAY OUT OF THE USE OF THIS SOFTWARE, EVEN IF ADVISED OF THE
# POSSIBILITY OF SUCH DAMAGE.

from __future__ import absolute_import
import logging
import os
import sys

import mitogen.core
import mitogen.utils


class Handler(logging.Handler):
    """
    Use Mitogen's log format, but send the result to a Display method.
    """
    def __init__(self, method):
        super(Handler, self).__init__()
        self.formatter = mitogen.utils.log_get_formatter(usec=True)
        self.method = method

    def emit(self, record):
        msg = self.format(record)
        self.method('[pid %d] %s' % (os.getpid(), msg))


def find_display():
    """
    Find the CLI tool's display variable somewhere up the stack. Why god why,
    right? Because it's the the simplest way to get access to the verbosity
    configured on the command line.
    """
    f = sys._getframe()
    while f:
        if 'display' in f.f_locals:
            return f.f_locals['display']
        f = f.f_back


def setup():
    """
    Install a handler for Mitogen's logger to redirect it into the Ansible
    display framework, and prevent propagation to the root logger.
    """
    display = find_display()

    logging.getLogger('ansible_mitogen').handlers = [Handler(display.v)]
    logging.getLogger('ansible_mitogen').setLevel(logging.DEBUG)

    mitogen.core.LOG.handlers = [Handler(display.v)]
    mitogen.core.LOG.setLevel(logging.DEBUG)

    mitogen.core.IOLOG.handlers = [Handler(display.vvvv)]
    if display.verbosity > 3:
        mitogen.core.IOLOG.setLevel(logging.DEBUG)
        mitogen.core.IOLOG.propagate = False
