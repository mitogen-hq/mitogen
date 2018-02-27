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
import threading

import mitogen
import mitogen.master
import mitogen.service
import mitogen.unix
import mitogen.utils

import ansible.errors
import ansible.plugins.strategy.linear
import ansible_mitogen.mixins

try:
    from ansible.plugins.loader import action_loader
    from ansible.plugins.loader import connection_loader
except ImportError:  # Ansible <2.4
    from ansible.plugins import action_loader
    from ansible.plugins import connection_loader


def wrap_action_loader__get(name, *args, **kwargs):
    """
    While the mitogen strategy is active, trap action_loader.get() calls,
    augmenting any fetched class with ActionModuleMixin, which replaces various
    helper methods inherited from ActionBase with implementations that avoid
    the use of shell fragments wherever possible.

    Additionally catch attempts to instantiate the "normal" action with a task
    argument whose action is "async_status", and redirect it to a special
    implementation that fetches polls the task result via RPC.

    This is used instead of static subclassing as it generalizes to third party
    action modules outside the Ansible tree.
    """
    if ( name == 'normal' and 'task' in kwargs and
         kwargs['task'].action == 'async_status'):
        name = 'mitogen_async_status'

    klass = action_loader__get(name, class_only=True)
    if klass:
        wrapped_name = 'MitogenActionModule_' + name
        bases = (ansible_mitogen.mixins.ActionModuleMixin, klass)
        adorned_klass = type(str(name), bases, {})
        if kwargs.get('class_only'):
            return adorned_klass
        return adorned_klass(*args, **kwargs)


def wrap_connection_loader__get(name, play_context, new_stdin):
    """
    While the mitogen strategy is active, rewrite connection_loader.get() calls
    for the 'ssh' and 'local' transports into corresponding requests for the
    'mitogen' connection type, passing the original transport name into it as
    an argument, so that it can emulate the original type.
    """
    kwargs = {}
    if name in ('ssh', 'local'):
        kwargs['original_transport'] = name
        name = 'mitogen'
    return connection_loader__get(name, play_context, new_stdin, **kwargs)


class ContextService(mitogen.service.Service):
    """
    Used by worker processes connecting back into the top-level process to
    fetch the single Context instance corresponding to the supplied connection
    configuration, creating a matching connection if it does not exist.

    For connection methods and their parameters, refer to:
        http://mitogen.readthedocs.io/en/latest/api.html#context-factories

    This concentrates all SSH connections in the top-level process, which may
    become a bottleneck. There are multiple ways to fix that: 
        * creating one .local() child context per CPU and sharding connections
          between them, using the master process to route messages, or
        * as above, but having each child create a unique UNIX listener and
          having workers connect in directly.

    :param dict dct:
        Parameters passed to mitogen.master.Router.[method](). One key,
        "method", is popped from the dictionary and used to look up the method.

    :returns mitogen.master.Context:
        Corresponding Context instance.
    """
    handle = 500
    max_message_size = 1000

    def __init__(self, router):
        super(ContextService, self).__init__(router)
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
    """
    This strategy enhances the default "linear" strategy by arranging for
    various Mitogen services to be initialized in the Ansible top-level
    process, and for worker processes to grow support for using those top-level
    services to communicate with and execute modules on remote hosts.

    Mitogen:

        A private Broker IO multiplexer thread is created to dispatch IO
        between the local Router and any connected streams, including streams
        connected to Ansible WorkerProcesses, and SSH commands implementing
        connections to remote machines.

        A Router is created that implements message dispatch to any locally
        registered handlers, and message routing for remote streams. Router is
        the junction point through which WorkerProceses and remote SSH contexts
        can communicate.

        Router additionally adds message handlers for a variety of base
        services, review the Standard Handles section of the How It Works guide
        in the documentation.

        A ContextService is installed as a message handler in the master
        process and run on a private thread. It is responsible for accepting
        requests to establish new SSH connections from worker processes, and
        ensuring precisely one connection exists and is reused for subsequent
        playbook steps. The service presently runs in a single thread, so to
        begin with, new SSH connections are serialized.

        Finally a mitogen.unix listener is created through which WorkerProcess
        can establish a connection back into the master process, in order to
        avail of ContextService. A UNIX listener socket is necessary as there
        is no more sane mechanism to arrange for IPC between the Router in the
        master process, and the corresponding Router in the worker process.

    Ansible:

        PluginLoader monkey patches are installed to catch attempts to create
        connection and action plug-ins.

        For connection plug-ins, if the desired method is "local" or "ssh", it
        is redirected to the "mitogen" connection plug-in. That plug-in
        implements communication via a UNIX socket connection to the master,
        and uses ContextService running in the master to actually establish and
        manage the connection.

        For action plug-ins, the original class is looked up as usual, but a
        new subclass is created dynamically in order to mix-in
        ansible_mitogen.helpers.ActionModuleMixin, which overrides many of the
        methods usually inherited from ActionBase in order to replace them with
        pure-Python equivalents that avoid the use of shell.

        In particular, _execute_module() is overridden with an implementation
        that uses ansible_mitogen.helpers.run_module() executed in the target
        Context. run_module() implements module execution by importing the
        module as if it were a normal Python module, and capturing its output
        in the remote process. Since the Mitogen module loader is active in the
        remote process, all the heavy lifting of transferring the action module
        and its dependencies are automatically handled by Mitogen.
    """
    def _setup_master(self):
        """
        Construct a Router, Broker, and mitogen.unix listener
        """
        self.router = mitogen.master.Router()
        self.router.responder.whitelist_prefix('ansible')
        self.router.responder.whitelist_prefix('ansible_mitogen')
        self.listener = mitogen.unix.Listener(self.router)
        os.environ['MITOGEN_LISTENER_PATH'] = self.listener.path

    def _setup_services(self):
        """
        Construct a ContextService and a thread to service requests for it
        arriving from worker processes.
        """
        self.service = ContextService(self.router)
        self.service_thread = threading.Thread(target=self.service.run)
        self.service_thread.start()

    def _run_with_master(self, iterator, play_context, result):
        """
        Arrange for a mitogen.master.Router to be available for the duration of
        the strategy's real run() method.
        """
        mitogen.utils.log_to_file()
        self._setup_master()
        self._setup_services()
        try:
            return super(StrategyModule, self).run(iterator, play_context)
        finally:
            os.unlink(self.listener.path)
            self.router.broker.shutdown()
            self.service_thread.join(timeout=10)

    def _install_wrappers(self):
        """
        Install our PluginLoader monkey patches and update global variables
        with references to the real functions.
        """
        global action_loader__get
        action_loader__get = action_loader.get
        action_loader.get = wrap_action_loader__get

        global connection_loader__get
        connection_loader__get = connection_loader.get
        connection_loader.get = wrap_connection_loader__get

    def _remove_wrappers(self):
        """
        Uninstall the PluginLoader monkey patches.
        """
        action_loader.get = action_loader__get
        connection_loader.get = connection_loader__get

    def _add_connection_plugin_path(self):
        """
        Add the mitogen connection plug-in directory to the ModuleLoader path,
        avoiding the need for manual configuration.
        """
        basedir = os.path.dirname(os.path.dirname(__file__))
        connection_loader.add_directory(os.path.join(basedir, 'connection'))
        action_loader.add_directory(os.path.join(basedir, 'actions'))

    def run(self, iterator, play_context, result=0):
        self._add_connection_plugin_path()
        self._install_wrappers()
        try:
            return self._run_with_master(iterator, play_context, result)
        finally:
            self._remove_wrappers()
