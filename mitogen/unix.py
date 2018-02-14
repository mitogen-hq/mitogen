# Copyright 2017, David Wilson
#
# Redistribution and use in source and binary forms, with or without
# modification, are permitted provided that the following conditions are met:
#
# 1. Redistributions of source code must retain the above copyright notice, this
# list of conditions and the following disclaimer.
#
# 2. Redistributions in binary form must reproduce the above copyright notice,
# this list of conditions and the following disclaimer in the documentation
# and/or other materials provided with the distribution.
#
# 3. Neither the name of the copyright holder nor the names of its contributors
# may be used to endorse or promote products derived from this software without
# specific prior written permission.
#
# THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS" AND
# ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE IMPLIED
# WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE
# DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT HOLDER OR CONTRIBUTORS BE LIABLE
# FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL
# DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR
# SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER
# CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY,
# OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE
# OF THIS SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.

"""
Permit connection of additional contexts that may act with the authority of
this context.
"""

import errno
import os
import socket
import struct
import tempfile

import mitogen.core
import mitogen.master

from mitogen.core import LOG


def is_path_dead(path):
    s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    try:
        s.connect(path)
    except socket.error, e:
        if e[0] in (errno.ECONNREFUSED, errno.ENOENT):
            return True
        return False


class Listener(mitogen.core.BasicStream):
    keep_alive = True
    def __init__(self, router, path=None, backlog=30):
        self._router = router
        self.path = path or tempfile.mktemp(prefix='mitogen_unix_')
        self._sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)

        if os.path.exists(self.path) and is_path_dead(self.path):
            LOG.debug('%r: deleting stale %r', self, self.path)
            os.unlink(self.path)

        self._sock.bind(self.path)
        os.chmod(self.path, 0600)
        self._sock.listen(backlog)
        mitogen.core.set_nonblock(self._sock.fileno())
        mitogen.core.set_cloexec(self._sock.fileno())
        self.path = self._sock.getsockname()
        self.receive_side = mitogen.core.Side(self, self._sock.fileno())
        router.broker.start_receive(self)

    def on_receive(self, broker):
        sock, _ = self._sock.accept()
        context_id = self._router.id_allocator.allocate()
        context = mitogen.master.Context(self._router, context_id)
        stream = mitogen.core.Stream(self._router, context_id)
        stream.accept(sock.fileno(), sock.fileno())
        stream.auth_id = mitogen.context_id
        self._router.register(context, stream)
        sock.send(struct.pack('>LL', context_id, mitogen.context_id))
        sock.close()


def connect(path):
    LOG.debug('unix.connect(path=%r)', path)
    sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    sock.connect(path)
    mitogen.context_id, remote_id = struct.unpack('>LL', sock.recv(8))
    mitogen.parent_id = remote_id
    mitogen.parent_ids = [remote_id]

    LOG.debug('unix.connect(): local ID is %r, remote is %r',
              mitogen.context_id, remote_id)

    router = mitogen.master.Router()
    stream = mitogen.core.Stream(router, remote_id)
    stream.accept(sock.fileno(), sock.fileno())

    context = mitogen.master.Context(router, remote_id)
    router.register(context, stream)

    mitogen.core.listen(router.broker, 'shutdown',
        lambda: router.disconnect_stream(stream))

    sock.close()
    return router, context
