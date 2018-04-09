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

"""
Classes in this file define Mitogen 'services' that run (initially) within the
connection multiplexer process that is forked off the top-level controller
process.

Once a worker process connects to a multiplexer process
(Connection._connect()), it communicates with these services to establish new
connections, grant access to files by children, and register for notification
when a child has completed a job.
"""

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
    Used by workers to fetch the single Context instance corresponding to a
    connection configuration, creating the matching connection if it does not
    exist.

    For connection methods and their parameters, see:
        https://mitogen.readthedocs.io/en/latest/api.html#context-factories

    This concentrates connections in the top-level process, which may become a
    bottleneck. The bottleneck can be removed using per-CPU connection
    processes and arranging for the worker to select one according to a hash of
    the connection parameters (sharding).
    """
    handle = 500
    max_message_size = 1000

    @mitogen.service.expose(mitogen.service.AllowParents())
    @mitogen.service.arg_spec({
        'method_name': str
    })
    def connect(self, method_name, discriminator=None, **kwargs):
        """
        Return a Context referring to an established connection with the given
        configuration, establishing a new connection as necessary.

        :param dict dct:
            Parameters passed to `mitogen.master.Router.[method]()`.

            * The `method` key is popped from the dictionary and used to look
              up the Mitogen connection method.
            * The `discriminator` key is mixed into the key used to select an
              existing connection, but popped from the list of arguments passed
              to the connection method.

        :returns tuple:
            Tuple of `(context, home_dir)`, where:
                * `context` is the mitogen.master.Context referring to the
                  target context.
                * `home_dir` is a cached copy of the remote directory.
        """
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
        # return value somewhere, but logs will catch a failure anyway.
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
    """
    handle = 501
    max_message_size = 1000
    unregistered_msg = 'Path is not registered with FileService.'

    def __init__(self, router):
        super(FileService, self).__init__(router)
        self._paths = {}

    @mitogen.service.expose(policy=mitogen.service.AllowParents())
    @mitogen.service.arg_spec({
        'path': basestring
    })
    def register(self, path):
        """
        Authorize a path for access by child contexts. Calling this repeatedly
        with the same path is harmless.

        :param str path:
            File path.
        """
        if path not in self._paths:
            LOG.debug('%r: registering %r', self, path)
            with open(path, 'rb') as fp:
                self._paths[path] = zlib.compress(fp.read())

    @mitogen.service.expose(policy=mitogen.service.AllowAny())
    @mitogen.service.arg_spec({
        'path': basestring
    })
    def fetch(self, path):
        """
        Fetch a file's data.

        :param str path:
            File path.

        :returns:
            The file data.

        :raises mitogen.core.CallError:
            The path was not registered.
        """
        if path not in self._paths:
            raise mitogen.core.CallError(self.unregistered_msg)

        LOG.debug('Serving %r', path)
        return self._paths[path]


class JobResultService(mitogen.service.Service):
    """
    Receive the result of a task from a child and forward it to interested
    listeners. If no listener exists, store the result until it is requested.

    Storing results in an intermediary service allows:

    * the lifetime of the worker to be decoupled from the lifetime of the job,
    * for new and unrelated workers to request the job result after the original
      worker that spawned it has exitted,
    * for synchronous and asynchronous jobs to be treated identically,
    * for latency-free polling and waiting on job results, and
    * for Ansible job IDs to be be used to refer to a job in preference to
      Mitogen-internal identifiers such as Sender and Context.

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
        """
        Register to receive the result of a job when it becomes available.

        :param str job_id:
            Job ID to listen for.
        :param mitogen.core.Sender sender:
            Sender on which to deliver the job result.
        """
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
        """
        Return a job's result if it is available, otherwise return immediately.
        The job result is forgotten once it has been returned by this method.

        :param str job_id:
            Job ID to return.
        :returns:
            Job result dictionary, or :data:`None`.
        """
        LOG.debug('%r.get(job_id=%r)', self, job_id)
        with self._lock:
            return self._result_by_job_id.pop(job_id, None)

    @mitogen.service.expose(mitogen.service.AllowAny())
    @mitogen.service.arg_spec({
        'job_id': basestring,
        'result': dict
    })
    def push(self, job_id, result):
        """
        Deliver a job's result from a child context, notifying any listener
        registred via :meth:`listen` of the result.

        :param str job_id:
            Job ID whose result is being pushed.
        :param dict result:
            Job result dictionary.
        """
        LOG.debug('%r.push(job_id=%r, result=%r)', self, job_id, result)
        with self._lock:
            if job_id in self._result_by_job_id:
                raise Error('Result already exists for job: %s' % (job_id,))
            sender = self._sender_by_job_id.pop(job_id, None)
            if sender:
                sender.send(result)
            else:
                self._result_by_job_id[job_id] = result
