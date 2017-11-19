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
Functionality to allow a slave context to reconnect back to its master using a
plain TCP connection.
"""

import socket

import mitogen.core

from mitogen.core import LOG


class Listener(mitogen.core.BasicStream):
    def __init__(self, broker, address=None, backlog=30):
        self._broker = broker
        self._sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._sock.bind(address or ('0.0.0.0', 0))
        self._sock.listen(backlog)
        mitogen.core.set_cloexec(self._sock.fileno())
        self.address = self._sock.getsockname()
        self.receive_side = mitogen.core.Side(self, self._sock.fileno())
        broker.start_receive(self)

    def on_receive(self, broker):
        sock, addr = self._sock.accept()
        context = mitogen.core.Context(self._broker, name=addr)
        stream = mitogen.core.Stream(context)
        stream.accept(sock.fileno(), sock.fileno())


def listen(broker, address=None, backlog=30):
    """Listen on `address` for connections from newly spawned contexts."""
    return Listener(broker, address, backlog)


def connect(context):
    """Connect to a Broker at the address specified in our associated
    Context."""
    LOG.debug('%s.connect()', __name__)
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    self.receive_side = mitogen.core.Side(self, sock.fileno())
    self.transmit_side = mitogen.core.Side(self, sock.fileno())
    sock.connect(self._context.parent_addr)
    self.enqueue(0, self._context.name)
