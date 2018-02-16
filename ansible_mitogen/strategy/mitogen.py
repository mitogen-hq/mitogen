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

import ansible.errors
import ansible.plugins.strategy.linear
import ansible.plugins
import ansible_mitogen.mixins


def wrap_action_loader__get(name, *args, **kwargs):
    """
    Trap calls to the action plug-in loader, supplementing the type of any
    ActionModule with Mitogen's ActionModuleMixin before constructing it,
    causing the mix-in methods to override any inherited from Ansible's base
    class, replacing most shell use with pure Python equivalents.

    This is preferred to static subclassing as it generalizes to third party
    action modules existing outside the Ansible tree.
    """
    klass = action_loader__get(name, class_only=True)
    if klass:
        wrapped_name = 'MitogenActionModule_' + name
        bases = (ansible_mitogen.mixins.ActionModuleMixin, klass)
        adorned_klass = type(str(name), bases, {})
        if kwargs.get('class_only'):
            return adorned_klass
        return adorned_klass(*args, **kwargs)

action_loader__get = ansible.plugins.action_loader.get
ansible.plugins.action_loader.get = wrap_action_loader__get


def wrap_connection_loader__get(name, play_context, new_stdin):
    """
    """
    kwargs = {}
    if name in ('ssh', 'local'):
        kwargs['original_transport'] = name
        name = 'mitogen'
    return connection_loader__get(name, play_context, new_stdin, **kwargs)

connection_loader__get = ansible.plugins.connection_loader.get
ansible.plugins.connection_loader.get = wrap_connection_loader__get


class ContextProxyService(mitogen.service.Service):
    """
    Implement a service accessible from worker processes connecting back into
    the top-level process. The service yields an existing context matching a
    connection configuration if it exists, otherwise it constructs a new
    conncetion before returning it.
    """
    well_known_id = 500
    max_message_size = 1000

    def __init__(self, router):
        super(ContextProxyService, self).__init__(router)
        self._context_by_key = {}

    def validate_args(self, args):
        return isinstance(args, dict)

    def dispatch(self, dct, msg):
        key = repr(sorted(dct.items()))
        if key not in self._context_by_key:
            method = getattr(self.router, dct.pop('method'))
            self._context_by_key[key] = method(**dct)
        return self._context_by_key[key]


class StrategyModule(ansible.plugins.strategy.linear.StrategyModule):
    def __init__(self, *args, **kwargs):
        super(StrategyModule, self).__init__(*args, **kwargs)
        self.add_connection_plugin_path()

    def add_connection_plugin_path(self):
        """
        Automatically add the connection plug-in directory to the ModuleLoader
        path, slightly reduces end-user configuration.
        """
        # ansible_mitogen base directory:
        basedir = os.path.dirname(os.path.dirname(__file__))
        conn_dir = os.path.join(basedir, 'connection')
        ansible.plugins.connection_loader.add_directory(conn_dir)

    def run(self, iterator, play_context, result=0):
        self.router = mitogen.master.Router()
        self.router.responder.whitelist_prefix('ansible')
        self.router.responder.whitelist_prefix('ansible_mitogen')
        self.listener = mitogen.unix.Listener(self.router)
        os.environ['LISTENER_SOCKET_PATH'] = self.listener.path

        self.service = ContextProxyService(self.router)
        #mitogen.utils.log_to_file(level='DEBUG', io=False)

        import threading
        th = threading.Thread(target=self.service.run)
        th.setDaemon(True)
        th.start()

        try:
            return super(StrategyModule, self).run(iterator, play_context)
        finally:
            self.router.broker.shutdown()
            os.unlink(self.listener.path)
