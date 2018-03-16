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

"""
Basic signal handler for dumping thread stacks.
"""

import difflib
import os
import signal
import sys
import threading
import time
import traceback


_last = None


def format_stacks():
    name_by_id = {
        t.ident: t.name
        for t in threading.enumerate()
    }

    l = ['', '']
    for threadId, stack in sys._current_frames().items():
        l += ["# PID %d ThreadID: (%s) %s; %r" % (
            os.getpid(),
            name_by_id.get(threadId, '<no name>'),
            threadId,
            stack,
        )]

        for filename, lineno, name, line in traceback.extract_stack(stack):
            l += [
                'File: "%s", line %d, in %s' % (
                    filename,
                    lineno,
                    name
                )
            ]
            if line:
                l += ['    ' + line.strip()]
        l += ['']

    l += ['', '']
    return '\n'.join(l)


def _handler(*_):
    global _last

    s = format_stacks()
    fp = open('/dev/tty', 'w', 1)
    fp.write(s)

    if _last:
        fp.write('\n')
        diff = list(difflib.unified_diff(
            a=_last.splitlines(),
            b=s.splitlines(),
            fromfile='then',
            tofile='now'
        ))

        if diff:
            fp.write('\n'.join(diff))
        else:
            fp.write('(no change since last time)\n')
    _last = s


def install_handler():
    signal.signal(signal.SIGUSR2, _handler)


def _thread_main():
    while True:
        time.sleep(7)
        l = format_stacks()
        open('/tmp/stack.%s.log' % (os.getpid(),), 'wb', 65535).write(l)
        break


def dump_periodically():
    th = threading.Thread(target=main)
    th.setDaemon(True)
    th.start()
