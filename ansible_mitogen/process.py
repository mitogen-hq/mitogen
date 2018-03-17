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
import os
import socket
import sys
import threading

import mitogen
import mitogen.core
import mitogen.master
import mitogen.parent
import mitogen.service
import mitogen.unix
import mitogen.utils

import ansible_mitogen.logging
import ansible_mitogen.services


class MuxProcess(object):
    """
    This implements a process forked from the Ansible top-level process as a
    safe place to contain the Mitogen IO multiplexer thread, keeping its use of
    the logging package (and the logging package's heavy use of locks) far away
    from the clutches of os.fork(), which is used continuously in the top-level
    process.

    The problem with running the multiplexer in that process is that should the
    multiplexer thread be in the process of emitting a log entry (and holding
    its lock) at the point of fork, in the child, the first attempt to log any
    log entry using the same handler will deadlock the child, as in the memory
    image the child received, the lock will always be marked held.
    """

    #: In the top-level process, this references one end of a socketpair(),
    #: which the MuxProcess blocks reading from in order to determine when
    #: the master process dies. Once the read returns, the MuxProcess will
    #: begin shutting itself down.
    worker_sock = None

    #: In the worker process, this references the other end of
    #: :py:attr:`worker_sock`.
    child_sock = None

    #: In the top-level process, this is the PID of the single MuxProcess
    #: that was spawned.
    worker_pid = None

    #: In both processes, this is the temporary UNIX socket used for
    #: forked WorkerProcesses to contact the MuxProcess
    unix_listener_path = None

    #: Singleton.
    _instance = None

    @classmethod
    def start(cls):
        if cls.worker_sock is not None:
            return

        cls.unix_listener_path = mitogen.unix.make_socket_path()
        cls.worker_sock, cls.child_sock = socket.socketpair()
        mitogen.core.set_cloexec(cls.worker_sock)
        mitogen.core.set_cloexec(cls.child_sock)

        cls.child_pid = os.fork()
        ansible_mitogen.logging.setup()
        if cls.child_pid:
            cls.child_sock.close()
            cls.child_sock = None
            cls.worker_sock.recv(1)
        else:
            cls.worker_sock.close()
            cls.worker_sock = None
            self = cls()
            self.run()
            sys.exit()

    def run(self):
        self._setup_master()
        self._setup_services()
        self.child_sock.send('1')
        try:
            self.child_sock.recv(1)
        except Exception, e:
            print 'do e', e
            pass

    def _setup_master(self):
        """
        Construct a Router, Broker, and mitogen.unix listener
        """
        self.router = mitogen.master.Router()
        self.router.responder.whitelist_prefix('ansible')
        self.router.responder.whitelist_prefix('ansible_mitogen')
        mitogen.core.listen(self.router.broker, 'shutdown', self.on_broker_shutdown)
        self.listener = mitogen.unix.Listener(
            router=self.router,
            path=self.unix_listener_path,
        )
        if 'MITOGEN_ROUTER_DEBUG' in os.environ:
            self.router.enable_debug()

    def _setup_services(self):
        """
        Construct a ContextService and a thread to service requests for it
        arriving from worker processes.
        """
        self.service = ansible_mitogen.services.ContextService(self.router)
        self.service_thread = threading.Thread(target=self.service.run)
        self.service_thread.start()

    def on_broker_shutdown(self):
        """
        Respond to the Router shutdown (indirectly triggered through exit of
        the main thread) by unlinking the listening socket. Ideally this would
        happen explicitly, but Ansible provides no hook to allow it.
        """
        os.unlink(self.listener.path)
        self.service_thread.join(timeout=10)
