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


def validate_arg_spec(spec, args):
    for name in spec:
        try:
            obj = args[name]
        except KeyError:
            raise mitogen.core.CallError(
                'Required argument %r missing.' % (name,)
            )

        if not isinstance(obj, spec[name]):
            raise mitogen.core.CallError(
                'Argument %r type incorrect, got %r, expected %r' % (
                    name,
                    type(obj),
                    spec[name]
                )
            )


def arg_spec(spec):
    """
    Annotate a method as requiring arguments with a specific type. This only
    validates required arguments. For optional arguments, write a manual check
    within the function.

    ::

        @mitogen.service.arg_spec({
            'path': str
        })
        def fetch_path(self, path, optional=None):
            ...

    :param dict spec:
        Mapping from argument name to expected type.
    """
    def wrapper(func):
        func.mitogen_service__arg_spec = spec
        return func
    return wrapper


def expose(policy):
    """
    Annotate a method to permit access to contexts matching an authorization
    policy. The annotation may be specified multiple times. Methods lacking any
    authorization policy are not accessible.

    ::

        @mitogen.service.expose(policy=mitogen.service.AllowParents())
        def unsafe_operation(self):
            ...

    :param mitogen.service.Policy policy:
        The policy to require.
    """
    def wrapper(func):
        func.mitogen_service__policies = (
            [policy] +
            getattr(func, 'mitogen_service__policies', [])
        )
        return func
    return wrapper


class Service(object):
    #: Sentinel object to suppress reply generation, since returning ``None``
    #: will trigger a response message containing the pickled ``None``.
    NO_REPLY = object()

    #: If ``None``, a handle is dynamically allocated, otherwise the fixed
    #: integer handle to use.
    handle = None
    max_message_size = 0

    def __init__(self, router):
        self.router = router
        self.recv = mitogen.core.Receiver(router, self.handle)
        self.recv.service = self
        self.handle = self.recv.handle
        self.running = True

    def __repr__(self):
        return '%s.%s()' % (
            self.__class__.__module__,
            self.__class__.__name__,
        )

    def on_shutdown(self):
        """
        Called by Pool.shutdown() once the last worker thread has exitted.
        """

    def dispatch(self, args, msg):
        raise NotImplementedError()

    def _validate_message(self, msg):
        if len(msg.data) > self.max_message_size:
            raise mitogen.core.CallError('Message size exceeded.')

        pair = msg.unpickle(throw=False)
        if not (isinstance(pair, tuple) and
                len(pair) == 2 and
                isinstance(pair[0], basestring)):
            raise mitogen.core.CallError('Invalid message format.')

        method_name, kwargs = pair
        method = getattr(self, method_name, None)
        if method is None:
            raise mitogen.core.CallError('No such method exists.')

        policies = getattr(method, 'mitogen_service__policies', None)
        if not policies:
            raise mitogen.core.CallError('Method has no policies set.')

        if not all(p.is_authorized(self, msg) for p in policies):
            raise mitogen.core.CallError('Unauthorized')

        required = getattr(method, 'mitogen_service__arg_spec', {})
        validate_arg_spec(required, kwargs)
        return method_name, kwargs

    def _on_receive_message(self, msg):
        method_name, kwargs = self._validate_message(msg)
        method = getattr(self, method_name)
        if 'msg' in method.func_code.co_varnames:
            kwargs['msg'] = msg  # TODO: hack
        return method(**kwargs)

    def on_receive_message(self, msg):
        try:
            response = self._on_receive_message(msg)
            if response is not self.NO_REPLY:
                msg.reply(response)
        except mitogen.core.CallError:
            e = sys.exc_info()[1]
            LOG.warning('%r: call error: %s: %s', self, msg, e)
            msg.reply(e)
        except Exception:
            LOG.exception('While invoking %r.dispatch()', self)
            e = sys.exc_info()[1]
            msg.reply(mitogen.core.CallError(e))


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

    def key_from_request(self, method_name, kwargs):
        """
        Generate a deduplication key from the request. The default
        implementation returns a string based on a stable representation of the
        input dictionary generated by :py:func:`pprint.pformat`.
        """
        return pprint.pformat((method_name, kwargs))

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

    def _on_receive_message(self, msg):
        method_name, kwargs = self._validate_message(msg)
        key = self.key_from_request(method_name, kwargs)

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
            response = getattr(self, method_name)(**kwargs)
            self._produce_response(key, response)
        except mitogen.core.CallError:
            e = sys.exc_info()[1]
            self._produce_response(key, e)
        except Exception:
            e = sys.exc_info()[1]
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
        for service in self.services:
            service.on_shutdown()

    def _worker_run(self):
        while True:
            try:
                msg = self._select.get()
            except (mitogen.core.ChannelError, mitogen.core.LatchError):
                e = sys.exc_info()[1]
                LOG.info('%r: channel or latch closed, exitting: %s', self, e)
                return

            service = msg.receiver.service
            try:
                service.on_receive_message(msg)
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


def call_async(context, handle, method, kwargs):
    LOG.debug('service.call_async(%r, %r, %r, %r)',
              context, handle, method, kwargs)
    pair = (method, kwargs)
    msg = mitogen.core.Message.pickled(pair, handle=handle)
    return context.send_async(msg)


def call(context, handle, method, kwargs):
    recv = call_async(context, handle, method, kwargs)
    return recv.get().unpickle()
