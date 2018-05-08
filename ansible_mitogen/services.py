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
import grp
import logging
import os
import os.path
import pwd
import stat
import sys
import threading
import zlib

import mitogen
import mitogen.service
import ansible_mitogen.target


LOG = logging.getLogger(__name__)


class Error(Exception):
    pass


class ContextService(mitogen.service.Service):
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
    max_interpreters = int(os.getenv('MITOGEN_MAX_INTERPRETERS', '20'))

    def __init__(self, *args, **kwargs):
        super(ContextService, self).__init__(*args, **kwargs)
        self._lock = threading.Lock()
        #: Records the :meth:`get` result dict for successful calls, returned
        #: for identical subsequent calls. Keyed by :meth:`key_from_kwargs`.
        self._response_by_key = {}
        #: List of :class:`mitogen.core.Latch` awaiting the result for a
        #: particular key.
        self._latches_by_key = {}
        #: Mapping of :class:`mitogen.core.Context` -> reference count. Each
        #: call to :meth:`get` increases this by one. Calls to :meth:`put`
        #: decrease it by one.
        self._refs_by_context = {}
        #: List of contexts in creation order by via= parameter. When
        #: :attr:`max_interpreters` is reached, the most recently used context
        #: is destroyed to make room for any additional context.
        self._lru_by_via = {}
        #: :meth:`key_from_kwargs` result by Context.
        self._key_by_context = {}

    @mitogen.service.expose(mitogen.service.AllowParents())
    @mitogen.service.arg_spec({
        'context': mitogen.core.Context
    })
    def put(self, context):
        """
        Return a reference, making it eligable for recycling once its reference
        count reaches zero.
        """
        LOG.debug('%r.put(%r)', self, context)
        if self._refs_by_context.get(context, 0) == 0:
            LOG.warning('%r.put(%r): refcount was 0. shutdown_all called?',
                        self, context)
            return
        self._refs_by_context[context] -= 1

    def key_from_kwargs(self, **kwargs):
        """
        Generate a deduplication key from the request.
        """
        out = []
        stack = [kwargs]
        while stack:
            obj = stack.pop()
            if isinstance(obj, dict):
                stack.extend(sorted(obj.iteritems()))
            elif isinstance(obj, (list, tuple)):
                stack.extend(obj)
            else:
                out.append(str(obj))
        return ''.join(out)

    def _produce_response(self, key, response):
        """
        Reply to every waiting request matching a configuration key with a
        response dictionary, deleting the list of waiters when done.

        :param str key:
            Result of :meth:`key_from_kwargs`
        :param dict response:
            Response dictionary
        :returns:
            Number of waiters that were replied to.
        """
        self._lock.acquire()
        try:
            latches = self._latches_by_key.pop(key)
            count = len(latches)
            for latch in latches:
                latch.put(response)
        finally:
            self._lock.release()
        return count

    def _shutdown(self, context, lru=None, new_context=None):
        """
        Arrange for `context` to be shut down, and optionally add `new_context`
        to the LRU list while holding the lock.
        """
        LOG.info('%r._shutdown(): shutting down %r', self, context)
        context.shutdown()

        key = self._key_by_context[context]

        self._lock.acquire()
        try:
            del self._response_by_key[key]
            del self._refs_by_context[context]
            del self._key_by_context[context]
            if lru and context in lru:
                lru.remove(context)
            if new_context:
                lru.append(new_context)
        finally:
            self._lock.release()

    def _update_lru(self, new_context, spec, via):
        """
        Update the LRU ("MRU"?) list associated with the connection described
        by `kwargs`, destroying the most recently created context if the list
        is full. Finally add `new_context` to the list.
        """
        lru = self._lru_by_via.setdefault(via, [])
        if len(lru) < self.max_interpreters:
            lru.append(new_context)
            return

        for context in reversed(lru):
            if self._refs_by_context[context] == 0:
                break
        else:
            LOG.warning('via=%r reached maximum number of interpreters, '
                        'but they are all marked as in-use.', via)
            return

        self._shutdown(context, lru=lru, new_context=new_context)

    @mitogen.service.expose(mitogen.service.AllowParents())
    def shutdown_all(self):
        """
        For testing use, arrange for all connections to be shut down.
        """
        for context in list(self._key_by_context):
            self._shutdown(context)
        self._lru_by_via = {}

    def _on_stream_disconnect(self, stream):
        """
        Respond to Stream disconnection by deleting any record of contexts
        reached via that stream. This method runs in the Broker thread and must
        not to block.
        """
        # TODO: there is a race between creation of a context and disconnection
        # of its related stream. An error reply should be sent to any message
        # in _latches_by_key below.
        self._lock.acquire()
        try:
            for context, key in list(self._key_by_context.items()):
                if context.context_id in stream.routes:
                    LOG.info('Dropping %r due to disconnect of %r',
                             context, stream)
                    self._response_by_key.pop(key, None)
                    self._latches_by_key.pop(key, None)
                    self._refs_by_context.pop(context, None)
                    self._lru_by_via.pop(context, None)
                    self._refs_by_context.pop(context, None)
        finally:
            self._lock.release()

    def _connect(self, key, spec, via=None):
        """
        Actual connect implementation. Arranges for the Mitogen connection to
        be created and enqueues an asynchronous call to start the forked task
        parent in the remote context.

        :param key:
            Deduplication key representing the connection configuration.
        :param spec:
            Connection specification.
        :returns:
            Dict like::

                {
                    'context': mitogen.core.Context or None,
                    'home_dir': str or None,
                    'msg': str or None
                }

            Where either `msg` is an error message and the remaining fields are
            :data:`None`, or `msg` is :data:`None` and the remaining fields are
            set.
        """
        try:
            method = getattr(self.router, spec['method'])
        except AttributeError:
            raise Error('unsupported method: %(transport)s' % spec)

        context = method(via=via, unidirectional=True, **spec['kwargs'])
        if via and spec.get('enable_lru'):
            self._update_lru(context, spec, via)
        else:
            # For directly connected contexts, listen to the associated
            # Stream's disconnect event and use it to invalidate dependent
            # Contexts.
            stream = self.router.stream_by_id(context.context_id)
            mitogen.core.listen(stream, 'disconnect',
                                lambda: self._on_stream_disconnect(stream))

        home_dir = context.call(os.path.expanduser, '~')

        # We don't need to wait for the result of this. Ideally we'd check its
        # return value somewhere, but logs will catch a failure anyway.
        context.call_async(ansible_mitogen.target.init_child)

        if os.environ.get('MITOGEN_DUMP_THREAD_STACKS'):
            from mitogen import debug
            context.call(debug.dump_to_logger)

        self._key_by_context[context] = key
        self._refs_by_context[context] = 0
        return {
            'context': context,
            'home_dir': home_dir,
            'msg': None,
        }

    def _wait_or_start(self, spec, via=None):
        latch = mitogen.core.Latch()
        key = self.key_from_kwargs(via=via, **spec)
        self._lock.acquire()
        try:
            response = self._response_by_key.get(key)
            if response is not None:
                self._refs_by_context[response['context']] += 1
                latch.put(response)
                return latch

            latches = self._latches_by_key.setdefault(key, [])
            first = len(latches) == 0
            latches.append(latch)
        finally:
            self._lock.release()

        if first:
            # I'm the first requestee, so I will create the connection.
            try:
                response = self._connect(key, spec, via=via)
                count = self._produce_response(key, response)
                # Only record the response for non-error results.
                self._response_by_key[key] = response
                # Set the reference count to the number of waiters.
                self._refs_by_context[response['context']] += count
            except Exception:
                self._produce_response(key, sys.exc_info())

        return latch

    @mitogen.service.expose(mitogen.service.AllowParents())
    @mitogen.service.arg_spec({
        'stack': list
    })
    def get(self, msg, stack):
        """
        Return a Context referring to an established connection with the given
        configuration, establishing new connections as necessary.

        :param list stack:
            Connection descriptions. Each element is a dict containing 'method'
            and 'kwargs' keys describing the Router method and arguments.
            Subsequent elements are proxied via the previous.

        :returns dict:
            * context: mitogen.master.Context or None.
            * homedir: Context's home directory or None.
            * msg: StreamError exception text or None.
            * method_name: string failing method name.
        """
        via = None
        for spec in stack:
            try:
                result = self._wait_or_start(spec, via=via).get()
                if isinstance(result, tuple):  # exc_info()
                    e1, e2, e3 = result
                    raise e1, e2, e3
                via = result['context']
            except mitogen.core.StreamError as e:
                return {
                    'context': None,
                    'home_dir': None,
                    'method_name': spec['method'],
                    'msg': str(e),
                }

        return result


class StreamState(object):
    def __init__(self):
        #: List of [(Sender, file object)]
        self.jobs = []
        self.completing = {}
        #: In-flight byte count.
        self.unacked = 0
        #: Lock.
        self.lock = threading.Lock()


class FileService(mitogen.service.Service):
    """
    Streaming file server, used to serve small files like Ansible modules and
    huge files like ISO images. Paths must be registered by a trusted context
    before they will be served to a child.

    Transfers are divided among the physical streams that connect external
    contexts, ensuring each stream never has excessive data buffered in RAM,
    while still maintaining enough to fully utilize available bandwidth. This
    is achieved by making an initial bandwidth assumption, enqueueing enough
    chunks to fill that assumed pipe, then responding to delivery
    acknowledgements from the receiver by scheduling new chunks.

    Transfers proceed one-at-a-time per stream. When multiple contexts exist on
    a stream (e.g. one is the SSH account, another is a sudo account, and a
    third is a proxied SSH connection), each request is satisfied in turn
    before subsequent requests start flowing. This ensures when a stream is
    contended, priority is given to completing individual transfers rather than
    potentially aborting many partial transfers, causing the bandwidth to be
    wasted.

    Theory of operation:
        1. Trusted context (i.e. WorkerProcess) calls register(), making a
           file available to any untrusted context.
        2. Requestee context creates a mitogen.core.Receiver() to receive
           chunks, then calls fetch(path, recv.to_sender()), to set up the
           transfer.
        3. fetch() replies to the call with the file's metadata, then
           schedules an initial burst up to the window size limit (1MiB).
        4. Chunks begin to arrive in the requestee, which calls acknowledge()
           for each 128KiB received.
        5. The acknowledge() call arrives at FileService, which scheduled a new
           chunk to refill the drained window back to the size limit.
        6. When the last chunk has been pumped for a single transfer,
           Sender.close() is called causing the receive loop in
           target.py::_get_file() to exit, allowing that code to compare the
           transferred size with the total file size from the metadata.
        7. If the sizes mismatch, _get_file()'s caller is informed which will
           discard the result and log/raise an error.

    Shutdown:
        1. process.py calls service.Pool.shutdown(), which arranges for the
           service pool threads to exit and be joined, guranteeing no new
           requests can arrive, before calling Service.on_shutdown() for each
           registered service.
        2. FileService.on_shutdown() walks every in-progress transfer and calls
           Sender.close(), causing Receiver loops in the requestees to exit
           early. The size check fails and any partially downloaded file is
           discarded.
        3. Control exits _get_file() in every target, and graceful shutdown can
           proceed normally, without the associated thread needing to be
           forcefully killed.
    """
    handle = 501
    max_message_size = 1000
    unregistered_msg = 'Path is not registered with FileService.'
    context_mismatch_msg = 'sender= kwarg context must match requestee context'

    #: Burst size. With 1MiB and 10ms RTT max throughput is 100MiB/sec, which
    #: is 5x what SSH can handle on a 2011 era 2.4Ghz Core i5.
    window_size_bytes = 1048576

    def __init__(self, router):
        super(FileService, self).__init__(router)
        #: Mapping of registered path -> file size.
        self._metadata_by_path = {}
        #: Mapping of Stream->StreamState.
        self._state_by_stream = {}

    def _name_or_none(self, func, n, attr):
        try:
            return getattr(func(n), attr)
        except KeyError:
            return None

    @mitogen.service.expose(policy=mitogen.service.AllowParents())
    @mitogen.service.arg_spec({
        'path': basestring
    })
    def register(self, path):
        """
        Authorize a path for access by children. Repeat calls with the same
        path is harmless.

        :param str path:
            File path.
        """
        if path in self._metadata_by_path:
            return

        st = os.stat(path)
        if not stat.S_ISREG(st.st_mode):
            raise IOError('%r is not a regular file.' % (in_path,))

        LOG.debug('%r: registering %r', self, path)
        self._metadata_by_path[path] = {
            'size': st.st_size,
            'mode': st.st_mode,
            'owner': self._name_or_none(pwd.getpwuid, 0, 'pw_name'),
            'group': self._name_or_none(grp.getgrgid, 0, 'gr_name'),
            'mtime': st.st_mtime,
            'atime': st.st_atime,
        }

    def on_shutdown(self):
        """
        Respond to shutdown by sending close() to every target, allowing their
        receive loop to exit and clean up gracefully.
        """
        LOG.debug('%r.on_shutdown()', self)
        for stream, state in self._state_by_stream.items():
            state.lock.acquire()
            try:
                for sender, fp in reversed(state.jobs):
                    sender.close()
                    fp.close()
                    state.jobs.pop()
            finally:
                state.lock.release()

    # The IO loop pumps 128KiB chunks. An ideal message is a multiple of this,
    # odd-sized messages waste one tiny write() per message on the trailer.
    # Therefore subtract 10 bytes pickle overhead + 24 bytes header.
    IO_SIZE = mitogen.core.CHUNK_SIZE - (mitogen.core.Stream.HEADER_LEN + (
        len(
            mitogen.core.Message.pickled(
                mitogen.core.Blob(' ' * mitogen.core.CHUNK_SIZE)
            ).data
        ) - mitogen.core.CHUNK_SIZE
    ))

    def _schedule_pending_unlocked(self, state):
        """
        Consider the pending transfers for a stream, pumping new chunks while
        the unacknowledged byte count is below :attr:`window_size_bytes`. Must
        be called with the StreamState lock held.

        :param StreamState state:
            Stream to schedule chunks for.
        """
        while state.jobs and state.unacked < self.window_size_bytes:
            sender, fp = state.jobs[0]
            s = fp.read(self.IO_SIZE)
            if s:
                state.unacked += len(s)
                sender.send(mitogen.core.Blob(s))
            else:
                # File is done. Cause the target's receive loop to exit by
                # closing the sender, close the file, and remove the job entry.
                sender.close()
                fp.close()
                state.jobs.pop(0)

    @mitogen.service.expose(policy=mitogen.service.AllowAny())
    @mitogen.service.no_reply()
    @mitogen.service.arg_spec({
        'path': basestring,
        'sender': mitogen.core.Sender,
    })
    def fetch(self, path, sender, msg):
        """
        Start a transfer for a registered path.

        :param str path:
            File path.
        :param mitogen.core.Sender sender:
            Sender to receive file data.
        :returns:
            Dict containing the file metadata:

            * ``size``: File size in bytes.
            * ``mode``: Integer file mode.
            * ``owner``: Owner account name on host machine.
            * ``group``: Owner group name on host machine.
            * ``mtime``: Floating point modification time.
            * ``ctime``: Floating point change time.
        :raises Error:
            Unregistered path, or Sender did not match requestee context.
        """
        if path not in self._metadata_by_path:
            raise Error(self.unregistered_msg)
        if msg.src_id != sender.context.context_id:
            raise Error(self.context_mismatch_msg)

        LOG.debug('Serving %r', path)
        fp = open(path, 'rb', self.IO_SIZE)
        # Response must arrive first so requestee can begin receive loop,
        # otherwise first ack won't arrive until all pending chunks were
        # delivered. In that case max BDP would always be 128KiB, aka. max
        # ~10Mbit/sec over a 100ms link.
        msg.reply(self._metadata_by_path[path])

        stream = self.router.stream_by_id(sender.context.context_id)
        state = self._state_by_stream.setdefault(stream, StreamState())
        state.lock.acquire()
        try:
            state.jobs.append((sender, fp))
            self._schedule_pending_unlocked(state)
        finally:
            state.lock.release()

    @mitogen.service.expose(policy=mitogen.service.AllowAny())
    @mitogen.service.no_reply()
    @mitogen.service.arg_spec({
        'size': int,
    })
    @mitogen.service.no_reply()
    def acknowledge(self, size, msg):
        """
        Acknowledge bytes received by a transfer target, scheduling new chunks
        to keep the window full. This should be called for every chunk received
        by the target.
        """
        stream = self.router.stream_by_id(msg.src_id)
        state = self._state_by_stream[stream]
        state.lock.acquire()
        try:
            if state.unacked < size:
                LOG.error('%r.acknowledge(src_id %d): unacked=%d < size %d',
                          self, msg.src_id, state.unacked, size)
            state.unacked -= min(state.unacked, size)
            self._schedule_pending_unlocked(state)
        finally:
            state.lock.release()
