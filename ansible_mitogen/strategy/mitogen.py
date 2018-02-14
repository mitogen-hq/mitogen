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

from __future__ import absolute_import
import os

import mitogen
import mitogen.master
import mitogen.service
import mitogen.unix
import mitogen.utils
import ansible_mitogen.action.mitogen

import ansible.errors
import ansible.plugins.strategy.linear
import ansible.plugins


class ContextProxyService(mitogen.service.Service):
    well_known_id = 500
    max_message_size = 1000

    def __init__(self, router):
        super(ContextProxyService, self).__init__(router)
        self._context_by_id = {}

    def validate_args(self, args):
        return isinstance(args, dict)

    def dispatch(self, dct, msg):
        key = repr(sorted(dct.items()))
        if key not in self._context_by_id:
            method = getattr(self.router, dct.pop('method'))
            self._context_by_id[key] = method(**dct)
        return self._context_by_id[key]


class StrategyModule(ansible.plugins.strategy.linear.StrategyModule):
    def __init__(self, *args, **kwargs):
        super(StrategyModule, self).__init__(*args, **kwargs)
        self.add_connection_plugin_path()

    def add_connection_plugin_path(self):
        """Automatically add the connection plug-in directory to the
        ModuleLoader path, reduces end-user configuration."""
        # ansible_mitogen base directory:
        basedir = os.path.dirname(os.path.dirname(__file__))
        conn_dir = os.path.join(basedir, 'connection')
        ansible.plugins.connection_loader.add_directory(conn_dir)

    def run(self, iterator, play_context, result=0):
        self.router = mitogen.master.Router()
        self.listener = mitogen.unix.Listener(self.router)
        os.environ['LISTENER_SOCKET_PATH'] = self.listener.path

        self.service = ContextProxyService(self.router)
        mitogen.utils.log_to_file()

        if play_context.connection == 'ssh':
            play_context.connection = 'mitogen'

        import threading
        th = threading.Thread(target=self.service.run)
        th.setDaemon(True)
        th.start()

        real_get = ansible.plugins.action_loader.get
        def get(name, *args, **kwargs):
            if name == 'normal':
                return ansible_mitogen.action.mitogen.ActionModule(*args, **kwargs)
            return real_get(name, *args, **kwargs)
        ansible.plugins.action_loader.get = get

        try:
            return super(StrategyModule, self).run(iterator, play_context)
        finally:
            self.router.broker.shutdown()
            os.unlink(self.listener.path)
