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
import threading
import os

import mitogen
import mitogen.core
import mitogen.master
import mitogen.service
import mitogen.unix
import mitogen.utils

import ansible_mitogen.logging
import ansible_mitogen.services


class State(object):
    """
    Process-global state that should persist across playbook runs.
    """
    #: ProcessState singleton.
    _instance = None

    @classmethod
    def instance(cls):
        """
        Fetch the ProcessState singleton, constructing it as necessary.
        """
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def __init__(self):
        ansible_mitogen.logging.setup()
        self._setup_master()
        self._setup_services()

    def _setup_master(self):
        """
        Construct a Router, Broker, and mitogen.unix listener
        """
        self.router = mitogen.master.Router()
        self.router.responder.whitelist_prefix('ansible')
        self.router.responder.whitelist_prefix('ansible_mitogen')
        mitogen.core.listen(self.router.broker, 'shutdown', self.on_broker_shutdown)
        self.listener = mitogen.unix.Listener(self.router)
        os.environ['MITOGEN_LISTENER_PATH'] = self.listener.path
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
