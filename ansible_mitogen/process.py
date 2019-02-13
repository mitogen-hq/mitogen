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

from __future__ import absolute_import
import atexit
import errno
import logging
import os
import signal
import socket
import sys
import time

try:
    import faulthandler
except ImportError:
    faulthandler = None

import mitogen
import mitogen.core
import mitogen.debug
import mitogen.master
import mitogen.parent
import mitogen.service
import mitogen.unix
import mitogen.utils

import ansible
import ansible.constants as C
import ansible_mitogen.logging
import ansible_mitogen.services

from mitogen.core import b
import ansible_mitogen.affinity


LOG = logging.getLogger(__name__)

ANSIBLE_PKG_OVERRIDE = (
    u"__version__ = %r\n"
    u"__author__ = %r\n"
)


def clean_shutdown(sock):
    """
    Shut the write end of `sock`, causing `recv` in the worker process to wake
    up with a 0-byte read and initiate mux process exit, then wait for a 0-byte
    read from the read end, which will occur after the the child closes the
    descriptor on exit.

    This is done using :mod:`atexit` since Ansible lacks any more sensible hook
    to run code during exit, and unless some synchronization exists with
    MuxProcess, debug logs may appear on the user's terminal *after* the prompt
    has been printed.
    """
    sock.shutdown(socket.SHUT_WR)
    sock.recv(1)


def getenv_int(key, default=0):
    """
    Get an integer-valued environment variable `key`, if it exists and parses
    as an integer, otherwise return `default`.
    """
    try:
        return int(os.environ.get(key, str(default)))
    except ValueError:
        return default


def save_pid(name):
    """
    When debugging and profiling, it is very annoying to poke through the
    process list to discover the currently running Ansible and MuxProcess IDs,
    especially when trying to catch an issue during early startup. So here, if
    a magic environment variable set, stash them in hidden files in the CWD::

        alias muxpid="cat .ansible-mux.pid"
        alias anspid="cat .ansible-controller.pid"

        gdb -p $(muxpid)
        perf top -p $(anspid)
    """
    if os.environ.get('MITOGEN_SAVE_PIDS'):
        with open('.ansible-%s.pid' % (name,), 'w') as fp:
            fp.write(str(os.getpid()))


class MuxProcess(object):
    """
    Implement a subprocess forked from the Ansible top-level, as a safe place
    to contain the Mitogen IO multiplexer thread, keeping its use of the
    logging package (and the logging package's heavy use of locks) far away
    from the clutches of os.fork(), which is used continuously by the
    multiprocessing package in the top-level process.

    The problem with running the multiplexer in that process is that should the
    multiplexer thread be in the process of emitting a log entry (and holding
    its lock) at the point of fork, in the child, the first attempt to log any
    log entry using the same handler will deadlock the child, as in the memory
    image the child received, the lock will always be marked held.

    See https://bugs.python.org/issue6721 for a thorough description of the
    class of problems this worker is intended to avoid.
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

    #: A copy of :data:`os.environ` at the time the multiplexer process was
    #: started. It's used by mitogen_local.py to find changes made to the
    #: top-level environment (e.g. vars plugins -- issue #297) that must be
    #: applied to locally executed commands and modules.
    original_env = None

    #: In both processes, this is the temporary UNIX socket used for
    #: forked WorkerProcesses to contact the MuxProcess
    unix_listener_path = None

    #: Singleton.
    _instance = None

    @classmethod
    def start(cls, _init_logging=True):
        """
        Arrange for the subprocess to be started, if it is not already running.

        The parent process picks a UNIX socket path the child will use prior to
        fork, creates a socketpair used essentially as a semaphore, then blocks
        waiting for the child to indicate the UNIX socket is ready for use.

        :param bool _init_logging:
            For testing, if :data:`False`, don't initialize logging.
        """
        if cls.worker_sock is not None:
            return

        if faulthandler is not None:
            faulthandler.enable()

        mitogen.utils.setup_gil()
        cls.unix_listener_path = mitogen.unix.make_socket_path()
        cls.worker_sock, cls.child_sock = socket.socketpair()
        atexit.register(lambda: clean_shutdown(cls.worker_sock))
        mitogen.core.set_cloexec(cls.worker_sock.fileno())
        mitogen.core.set_cloexec(cls.child_sock.fileno())

        cls.profiling = os.environ.get('MITOGEN_PROFILING') is not None
        if cls.profiling:
            mitogen.core.enable_profiling()

        cls.original_env = dict(os.environ)
        cls.child_pid = os.fork()
        if _init_logging:
            ansible_mitogen.logging.setup()
        if cls.child_pid:
            save_pid('controller')
            ansible_mitogen.affinity.policy.assign_controller()
            cls.child_sock.close()
            cls.child_sock = None
            mitogen.core.io_op(cls.worker_sock.recv, 1)
        else:
            save_pid('mux')
            ansible_mitogen.affinity.policy.assign_muxprocess()
            cls.worker_sock.close()
            cls.worker_sock = None
            self = cls()
            self.worker_main()

    def worker_main(self):
        """
        The main function of for the mux process: setup the Mitogen broker
        thread and ansible_mitogen services, then sleep waiting for the socket
        connected to the parent to be closed (indicating the parent has died).
        """
        self._setup_master()
        self._setup_services()

        try:
            # Let the parent know our listening socket is ready.
            mitogen.core.io_op(self.child_sock.send, b('1'))
            # Block until the socket is closed, which happens on parent exit.
            mitogen.core.io_op(self.child_sock.recv, 1)
        finally:
            self.broker.shutdown()
            self.broker.join()

            # Test frameworks living somewhere higher on the stack of the
            # original parent process may try to catch sys.exit(), so do a C
            # level exit instead.
            os._exit(0)

    def _enable_router_debug(self):
        if 'MITOGEN_ROUTER_DEBUG' in os.environ:
            self.router.enable_debug()

    def _enable_stack_dumps(self):
        secs = getenv_int('MITOGEN_DUMP_THREAD_STACKS', default=0)
        if secs:
            mitogen.debug.dump_to_logger(secs=secs)

    def _setup_simplejson(self, responder):
        """
        We support serving simplejson for Python 2.4 targets on Ansible 2.3, at
        least so the package's own CI Docker scripts can run without external
        help, however newer versions of simplejson no longer support Python
        2.4. Therefore override any installed/loaded version with a
        2.4-compatible version we ship in the compat/ directory.
        """
        responder.whitelist_prefix('simplejson')

        # issue #536: must be at end of sys.path, in case existing newer
        # version is already loaded.
        compat_path = os.path.join(os.path.dirname(__file__), 'compat')
        sys.path.append(compat_path)

        for fullname, is_pkg, suffix in (
            (u'simplejson', True, '__init__.py'),
            (u'simplejson.decoder', False, 'decoder.py'),
            (u'simplejson.encoder', False, 'encoder.py'),
            (u'simplejson.scanner', False, 'scanner.py'),
        ):
            path = os.path.join(compat_path, 'simplejson', suffix)
            fp = open(path, 'rb')
            try:
                source = fp.read()
            finally:
                fp.close()

            responder.add_source_override(
                fullname=fullname,
                path=path,
                source=source,
                is_pkg=is_pkg,
            )

    def _setup_responder(self, responder):
        """
        Configure :class:`mitogen.master.ModuleResponder` to only permit
        certain packages, and to generate custom responses for certain modules.
        """
        responder.whitelist_prefix('ansible')
        responder.whitelist_prefix('ansible_mitogen')
        self._setup_simplejson(responder)

        # Ansible 2.3 is compatible with Python 2.4 targets, however
        # ansible/__init__.py is not. Instead, executor/module_common.py writes
        # out a 2.4-compatible namespace package for unknown reasons. So we
        # copy it here.
        responder.add_source_override(
            fullname='ansible',
            path=ansible.__file__,
            source=(ANSIBLE_PKG_OVERRIDE % (
                ansible.__version__,
                ansible.__author__,
            )).encode(),
            is_pkg=True,
        )

    def _setup_master(self):
        """
        Construct a Router, Broker, and mitogen.unix listener
        """
        self.broker = mitogen.master.Broker(install_watcher=False)
        self.router = mitogen.master.Router(
            broker=self.broker,
            max_message_size=4096 * 1048576,
        )
        self._setup_responder(self.router.responder)
        mitogen.core.listen(self.broker, 'shutdown', self.on_broker_shutdown)
        mitogen.core.listen(self.broker, 'exit', self.on_broker_exit)
        self.listener = mitogen.unix.Listener(
            router=self.router,
            path=self.unix_listener_path,
            backlog=C.DEFAULT_FORKS,
        )
        self._enable_router_debug()
        self._enable_stack_dumps()

    def _setup_services(self):
        """
        Construct a ContextService and a thread to service requests for it
        arriving from worker processes.
        """
        self.pool = mitogen.service.Pool(
            router=self.router,
            services=[
                mitogen.service.FileService(router=self.router),
                mitogen.service.PushFileService(router=self.router),
                ansible_mitogen.services.ContextService(self.router),
                ansible_mitogen.services.ModuleDepService(self.router),
            ],
            size=getenv_int('MITOGEN_POOL_SIZE', default=32),
        )
        LOG.debug('Service pool configured: size=%d', self.pool.size)

    def on_broker_shutdown(self):
        """
        Respond to broker shutdown by beginning service pool shutdown. Do not
        join on the pool yet, since that would block the broker thread which
        then cannot clean up pending handlers, which is required for the
        threads to exit gracefully.
        """
        # In normal operation we presently kill the process because there is
        # not yet any way to cancel connect().
        self.pool.stop(join=self.profiling)

    def on_broker_exit(self):
        """
        Respond to the broker thread about to exit by sending SIGTERM to
        ourself. In future this should gracefully join the pool, but TERM is
        fine for now.
        """
        if not self.profiling:
            # In normal operation we presently kill the process because there is
            # not yet any way to cancel connect(). When profiling, threads
            # including the broker must shut down gracefully, otherwise pstats
            # won't be written.
            os.kill(os.getpid(), signal.SIGTERM)
