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
import logging
import os.path
import threading
import zlib

import mitogen
import mitogen.service
import ansible_mitogen.target


LOG = logging.getLogger(__name__)


class Error(Exception):
    pass


class ContextService(mitogen.service.DeduplicatingService):
    """
    Used by worker processes connecting back into the top-level process to
    fetch the single Context instance corresponding to the supplied connection
    configuration, creating a matching connection if it does not exist.

    For connection methods and their parameters, refer to:
        https://mitogen.readthedocs.io/en/latest/api.html#context-factories

    This concentrates all SSH connections in the top-level process, which may
    become a bottleneck. There are multiple ways to fix that:
        * creating one .local() child context per CPU and sharding connections
          between them, using the master process to route messages, or
        * as above, but having each child create a unique UNIX listener and
          having workers connect in directly.

    :param dict dct:
        Parameters passed to `mitogen.master.Router.[method]()`.

        * The `method` key is popped from the dictionary and used to look up
          the Mitogen connection method.
        * The `discriminator` key is mixed into the key used to select an
          existing connection, but popped from the list of arguments passed to
          the connection method.

    :returns tuple:
        Tuple of `(context, home_dir)`, where:
            * `context` is the mitogen.master.Context referring to the target
              context.
            * `home_dir` is a cached copy of the remote directory.

    mitogen.master.Context:
        Corresponding Context instance.
    """
    handle = 500
    max_message_size = 1000

    @mitogen.service.expose(mitogen.service.AllowParents())
    @mitogen.service.arg_spec({
        'method_name': str
    })
    def connect(self, method_name, discriminator=None, **kwargs):
        method = getattr(self.router, method_name, None)
        if method is None:
            raise Error('no such Router method: %s' % (method_name,))
        try:
            context = method(**kwargs)
        except mitogen.core.StreamError as e:
            return {
                'context': None,
                'home_dir': None,
                'msg': str(e),
            }

        home_dir = context.call(os.path.expanduser, '~')

        # We don't need to wait for the result of this. Ideally we'd check its
        # return value somewhere, but logs will catch any failures anyway.
        context.call_async(ansible_mitogen.target.start_fork_parent)
        return {
            'context': context,
            'home_dir': home_dir,
            'msg': None,
        }


class FileService(mitogen.service.Service):
    """
    Primitive latency-inducing file server for old-style incantations of the
    module runner. This is to be replaced later with a scheme that forwards
    files known to be missing without the target having to ask for them,
    avoiding a corresponding roundtrip per file.

    Paths must be explicitly added to the service by a trusted context before
    they will be served to an untrusted context.

    :param tuple args:
        Tuple of `(cmd, path)`, where:
            - cmd: one of "register", "fetch", where:
                - register: register a file that may be fetched
                - fetch: fetch a file that was previously registered
            - path: key of the file to fetch or register

    :returns:
        Returns ``None` for "register", or the file data for "fetch".

    :raises mitogen.core.CallError:
        Security violation occurred, either path not registered, or attempt to
        register path from unprivileged context.
    """
    handle = 501
    max_message_size = 1000
    policies = (
        mitogen.service.AllowAny(),
    )

    unprivileged_msg = 'Cannot register from unprivileged context.'
    unregistered_msg = 'Path is not registered with FileService.'

    def __init__(self, router):
        super(FileService, self).__init__(router)
        self._paths = {}

    @mitogen.service.expose(policy=mitogen.service.AllowParents())
    @mitogen.service.arg_spec({
        'path': basestring
    })
    def register(self, path):
        if path not in self._paths:
            LOG.info('%r: registering %r', self, path)
            with open(path, 'rb') as fp:
                self._paths[path] = zlib.compress(fp.read())

    @mitogen.service.expose(policy=mitogen.service.AllowAny())
    @mitogen.service.arg_spec({
        'path': basestring
    })
    def fetch(self, path):
        if path not in self._paths:
            raise mitogen.core.CallError(self.unregistered_msg)

        LOG.debug('Serving %r', path)
        return self._paths[path]


class JobResultService(mitogen.service.Service):
    """
    Receive the result of a task from a child and forward it to interested
    listeners. If no listener exists, store the result until it is requested.

    Results are keyed by job ID.
    """
    handle = 502
    max_message_size = 1048576 * 64

    def __init__(self, router):
        super(JobResultService, self).__init__(router)
        self._lock = threading.Lock()
        self._result_by_job_id = {}
        self._sender_by_job_id = {}

    @mitogen.service.expose(mitogen.service.AllowParents())
    @mitogen.service.arg_spec({
        'job_id': str,
        'sender': mitogen.core.Sender,
    })
    def listen(self, job_id, sender):
        LOG.debug('%r.listen(job_id=%r, sender=%r)', self, job_id, sender)
        with self._lock:
            if job_id in self._sender_by_job_id:
                raise Error('Listener already exists for job: %s' % (job_id,))
            self._sender_by_job_id[job_id] = sender

    @mitogen.service.expose(mitogen.service.AllowParents())
    @mitogen.service.arg_spec({
        'job_id': basestring,
    })
    def get(self, job_id):
        LOG.debug('%r.get(job_id=%r)', self, job_id)
        with self._lock:
            return self._result_by_job_id.pop(job_id, None)

    @mitogen.service.expose(mitogen.service.AllowAny())
    @mitogen.service.arg_spec({
        'job_id': basestring,
        'result': dict
    })
    def push(self, job_id, result):
        LOG.debug('%r.push(job_id=%r, result=%r)', self, job_id, result)
        with self._lock:
            if job_id in self._result_by_job_id:
                raise Error('Result already exists for job: %s' % (job_id,))
            sender = self._sender_by_job_id.pop(job_id, None)
            if sender:
                sender.send(result)
            else:
                self._result_by_job_id[job_id] = result
