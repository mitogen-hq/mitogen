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
