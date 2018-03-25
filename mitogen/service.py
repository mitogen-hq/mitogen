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

import pprint
import sys
import threading

import mitogen.core
import mitogen.master
from mitogen.core import LOG


class Policy(object):
    """
    Base security policy.
    """
    def is_authorized(self, service, msg):
        raise NotImplementedError()


class AllowAny(Policy):
    def is_authorized(self, service, msg):
        return True


class AllowParents(Policy):
    def is_authorized(self, service, msg):
        return (msg.auth_id in mitogen.parent_ids or
                msg.auth_id == mitogen.context_id)


class Service(object):
    #: Sentinel object to suppress reply generation, since returning ``None``
    #: will trigger a response message containing the pickled ``None``.
    NO_REPLY = object()

    #: If ``None``, a handle is dynamically allocated, otherwise the fixed
    #: integer handle to use.
    handle = None
    max_message_size = 0

    #: Mapping from required key names to their required corresponding types,
    #: used by the default :py:meth:`validate_args` implementation to validate
    #: requests.
    required_args = {}

    #: Policies that must authorize each message. By default only parents are
    #: authorized.
    policies = (
        AllowParents(),
    )

    def __init__(self, router):
        self.router = router
        self.recv = mitogen.core.Receiver(router, self.handle)
        self.recv.service = self
        self.handle = self.recv.handle
        self.running = True

    def validate_args(self, args):
        return (
            isinstance(args, dict) and
            all(isinstance(args.get(k), t)
                for k, t in self.required_args.iteritems())
        )

    def dispatch(self, args, msg):
        raise NotImplementedError()

    def dispatch_one(self, msg):
        if not all(p.is_authorized(self, msg) for p in self.policies):
            LOG.error('%r: unauthorized message %r', self, msg)
            msg.reply(mitogen.core.CallError('Unauthorized'))
            return

        if len(msg.data) > self.max_message_size:
            LOG.error('%r: larger than permitted size: %r', self, msg)
            msg.reply(mitogen.core.CallError('Message size exceeded'))
            return

        args = msg.unpickle(throw=False)
        if  (args == mitogen.core._DEAD or
             isinstance(args, mitogen.core.CallError) or
             not self.validate_args(args)):
            LOG.warning('Received junk message: %r', args)
            return

        try:
            response = self.dispatch(args, msg)
            if response is not self.NO_REPLY:
                msg.reply(response)
        except Exception, e:
            LOG.exception('While invoking %r.dispatch()', self)
            msg.reply(mitogen.core.CallError(e))

    def run_once(self):
        try:
            msg = self.recv.get()
        except mitogen.core.ChannelError, e:
            # Channel closed due to broker shutdown, exit gracefully.
            LOG.debug('%r: channel closed: %s', self, e)
            self.running = False
            return

        self.dispatch_one(msg)

    def run(self):
        while self.running:
            self.run_once()


class DeduplicatingService(Service):
    """
    A service that deduplicates and caches expensive responses. Requests are
    deduplicated according to a customizable key, and the single expensive
    response is broadcast to all requestors.

    A side effect of this class is that processing of the single response is
    always serialized according to the result of :py:meth:`key_from_request`.

    Only one pool thread is blocked during generation of the response,
    regardless of the number of requestors.
    """
    def __init__(self, router):
        super(DeduplicatingService, self).__init__(router)
        self._responses = {}
        self._waiters = {}
        self._lock = threading.Lock()

    def key_from_request(self, args):
        """
        Generate a deduplication key from the request. The default
        implementation returns a string based on a stable representation of the
        input dictionary generated by :py:func:`pprint.pformat`.
        """
        return pprint.pformat(args)

    def get_response(self, args):
        raise NotImplementedError()

    def _produce_response(self, key, response):
        self._lock.acquire()
        try:
            assert key not in self._responses
            assert key in self._waiters
            self._responses[key] = response
            for msg in self._waiters.pop(key):
                msg.reply(response)
        finally:
            self._lock.release()

    def dispatch(self, args, msg):
        key = self.key_from_request(args)

        self._lock.acquire()
        try:
            if key in self._responses:
                return self._responses[key]

            if key in self._waiters:
                self._waiters[key].append(msg)
                return self.NO_REPLY

            self._waiters[key] = [msg]
        finally:
            self._lock.release()

        # I'm the unlucky thread that must generate the response.
        try:
            self._produce_response(key, self.get_response(args))
        except Exception, e:
            self._produce_response(key, mitogen.core.CallError(e))

        return self.NO_REPLY


class Pool(object):
    """
    Manage a pool of at least one thread that will be used to process messages
    for a collection of services.

    Internally this is implemented by subscribing every :py:class:`Service`'s
    :py:class:`mitogen.core.Receiver` using a single
    :py:class:`mitogen.master.Select`, then arranging for every thread to
    consume messages delivered to that select.

    In this way the threads are fairly shared by all available services, and no
    resources are dedicated to a single idle service.

    There is no penalty for exposing large numbers of services; the list of
    exposed services could even be generated dynamically in response to your
    program's configuration or its input data.
    """
    def __init__(self, router, services, size=1):
        assert size > 0
        self.router = router
        self.services = list(services)
        self.size = size
        self._select = mitogen.master.Select(
            receivers=[
                service.recv
                for service in self.services
            ],
            oneshot=False,
        )
        self._threads = []
        for x in xrange(size):
            thread = threading.Thread(
                name='mitogen.service.Pool.%x.worker-%d' % (id(self), x,),
                target=self._worker_main,
            )
            thread.start()
            self._threads.append(thread)

    def stop(self):
        self._select.close()
        for th in self._threads:
            th.join()

    def _worker_run(self):
        while True:
            try:
                msg = self._select.get()
            except (mitogen.core.ChannelError, mitogen.core.LatchError):
                e = sys.exc_info()[1]
                LOG.error('%r: channel or latch closed, exitting: %s', self, e)
                return

            service = msg.receiver.service
            try:
                service.dispatch_one(msg)
            except Exception:
                LOG.exception('While handling %r using %r', msg, service)

    def _worker_main(self):
        try:
            self._worker_run()
        except Exception:
            th = threading.currentThread()
            LOG.exception('%r: worker %r crashed', self, th.name)
            raise

    def __repr__(self):
        th = threading.currentThread()
        return 'mitogen.service.Pool(%#x, size=%d, th=%r)' % (
            id(self),
            self.size,
            th.name,
        )


def call(context, handle, obj):
    msg = mitogen.core.Message.pickled(obj, handle=handle)
    recv = context.send_async(msg)
    return recv.get().unpickle()
