# Copyright 2019, David Wilson
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

# !mitogen: minify_safe

"""
When operating in a mixed threading/forking environment, it is critical no
threads are active at the moment of fork, as they could be within critical
sections whose mutexes are snapshotted in the locked state in the fork child.

To permit unbridled Mitogen use in a forking program, a mechanism must exist to
temporarily halt any threads in operation -- namely the broker and any pool
threads.
"""

import os
import socket
import sys
import weakref

import mitogen.core


# List of weakrefs. On Python 2.4, mitogen.core registers its Broker on this
# list and mitogen.service registers its Pool too.
_brokers = weakref.WeakKeyDictionary()
_pools = weakref.WeakKeyDictionary()


def _notice_broker_or_pool(obj):
    if isinstance(obj, mitogen.core.Broker):
        _brokers[obj] = True
    else:
        _pools[obj] = True


def wrap_os__fork():
    corker = Corker(
        brokers=list(_brokers),
        pools=list(_pools),
    )
    try:
        corker.cork()
        return os__fork()
    finally:
        corker.uncork()


# If Python 2.4/2.5 where threading state is not fixed up, subprocess.Popen()
# may still deadlock due to the broker thread. In this case, pause os.fork() so
# that all active threads are paused during fork.
if sys.version_info < (2, 6):
    os__fork = os.fork
    os.fork = wrap_os__fork


class Corker(object):
    """
    Arrange for :class:`mitogen.core.Broker` and optionally
    :class:`mitogen.service.Pool` to be temporarily "corked" while fork
    operations may occur.

    Since this necessarily involves posting a message to every existent thread
    and verifying acknowledgement, it will never be a fast operation.
    """
    def __init__(self, brokers=(), pools=()):
        self.brokers = brokers
        self.pools = pools

    def _do_cork(self, s, wsock):
        try:
            try:
                while True:
                    # at least EINTR is possible. Do our best to keep handling
                    # outside the GIL in this case using sendall().
                    wsock.sendall(s)
            except socket.error:
                pass
        finally:
            wsock.close()

    def _cork_one(self, s, obj):
        """
        To ensure the target thread has all locks dropped, we ask it to write a
        large string to a socket with a small buffer that has O_NONBLOCK
        disabled. CPython will drop the GIL and enter the write() system call,
        where it will block until the socket buffer is drained, or the write
        side is closed. We can detect the thread has blocked outside of Python
        code by checking if the socket buffer has started to fill using a
        poller.
        """
        rsock, wsock = mitogen.parent.create_socketpair(size=4096)
        mitogen.core.set_cloexec(rsock.fileno())
        mitogen.core.set_cloexec(wsock.fileno())
        mitogen.core.set_block(wsock)  # gevent
        self._rsocks.append(rsock)
        obj.defer(self._do_cork, s, wsock)
        poller = mitogen.core.Poller()
        poller.start_receive(rsock.fileno())
        try:
            while True:
                for fd in poller.poll():
                    return
        finally:
            poller.close()

    def cork(self):
        """
        Arrange for the broker and optional pool to be paused with no locks
        held. This will not return until each thread acknowledges it has ceased
        execution.
        """
        s = 'CORK' * ((128 / 4) * 1024)
        self._rsocks = []
        for pool in self.pools:
            if not pool.closed:
                for x in range(pool.size):
                    self._cork_one(s, pool)
        for broker in self.brokers:
            if broker._alive:
                self._cork_one(s, broker)

    def uncork(self):
        """
        Arrange for paused threads to resume operation.
        """
        for rsock in self._rsocks:
            rsock.close()
