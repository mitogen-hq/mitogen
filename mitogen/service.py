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
import mitogen.select
from mitogen.core import LOG


DEFAULT_POOL_SIZE = 16
_pool = None


@mitogen.core.takes_router
def get_or_create_pool(size=None, router=None):
    global _pool
    if _pool is None:
        _pool = Pool(router, [], size=size or DEFAULT_POOL_SIZE)
    return _pool


@mitogen.core.takes_router
def _on_stub_call(router):
    """
    Called for each message received by the core.py stub CALL_SERVICE handler.
    Create the pool if it doesn't already exist, and push enqueued messages
    into the pool's receiver. This may be called more than once as the stub
    service handler runs in asynchronous context, while _on_stub_call() happens
    on the main thread. Multiple CALL_SERVICE may end up enqueued before Pool
    has a chance to install the real CALL_SERVICE handler.
    """
    pool = get_or_create_pool(router=router)
    mitogen.core._service_call_lock.acquire()
    try:
        for msg in mitogen.core._service_calls:
            pool._receiver._on_receive(msg)
        del mitogen.core._service_calls[:]
    finally:
        mitogen.core._service_call_lock.release()


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


def no_reply():
    """
    Annotate a method as one that does not generate a response. Messages sent
    by the method are done so explicitly. This can be used for fire-and-forget
    endpoints where the requestee never receives a reply.
    """
    def wrapper(func):
        func.mitogen_service__no_reply = True
        return func
    return wrapper


class Error(Exception):
    """
    Raised when an error occurs configuring a service or pool.
    """


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


class Activator(object):
    """
    """
    def is_permitted(self, mod_name, class_name, msg):
        return mitogen.core.has_parent_authority(msg)

    not_active_msg = (
        'Service %r is not yet activated in this context, and the '
        'caller is not privileged, therefore autoactivation is disabled.'
    )

    def activate(self, pool, service_name, msg):
        mod_name, _, class_name = service_name.rpartition('.')
        if not self.is_permitted(mod_name, class_name, msg):
            raise mitogen.core.CallError(self.not_active_msg, service_name)

        module = mitogen.core.import_module(mod_name)
        klass = getattr(module, class_name)
        service = klass(pool.router)
        pool.add(service)
        return service


class Invoker(object):
    def __init__(self, service):
        self.service = service

    def __repr__(self):
        return '%s(%s)' % (type(self).__name__, self.service)

    unauthorized_msg = (
        'Caller is not authorized to invoke %r of service %r'
    )

    def _validate(self, method_name, kwargs, msg):
        method = getattr(self.service, method_name, None)
        if method is None:
            raise mitogen.core.CallError('No such method: %r', method_name)

        policies = getattr(method, 'mitogen_service__policies', None)
        if not policies:
            raise mitogen.core.CallError('Method has no policies set.')

        if not all(p.is_authorized(self.service, msg) for p in policies):
            raise mitogen.core.CallError(
                self.unauthorized_msg,
                method_name,
                self.service.name()
            )

        required = getattr(method, 'mitogen_service__arg_spec', {})
        validate_arg_spec(required, kwargs)

    def _invoke(self, method_name, kwargs, msg):
        method = getattr(self.service, method_name)
        if 'msg' in method.func_code.co_varnames:
            kwargs['msg'] = msg  # TODO: hack

        no_reply = getattr(method, 'mitogen_service__no_reply', False)
        ret = None
        try:
            ret = method(**kwargs)
            if no_reply:
                return Service.NO_REPLY
            return ret
        except Exception:
            if no_reply:
                LOG.exception('While calling no-reply method %s.%s',
                              type(self).__name__, method.func_name)
            else:
                raise

    def invoke(self, method_name, kwargs, msg):
        self._validate(method_name, kwargs, msg)
        response = self._invoke(method_name, kwargs, msg)
        if response is not Service.NO_REPLY:
            msg.reply(response)


class DeduplicatingInvoker(Invoker):
    """
    A service that deduplicates and caches expensive responses. Requests are
    deduplicated according to a customizable key, and the single expensive
    response is broadcast to all requestors.

    A side effect of this class is that processing of the single response is
    always serialized according to the result of :py:meth:`key_from_request`.

    Only one pool thread is blocked during generation of the response,
    regardless of the number of requestors.
    """
    def __init__(self, service):
        super(DeduplicatingInvoker, self).__init__(service)
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

    def _invoke(self, method_name, kwargs, msg):
        key = self.key_from_request(method_name, kwargs)
        self._lock.acquire()
        try:
            if key in self._responses:
                return self._responses[key]

            if key in self._waiters:
                self._waiters[key].append(msg)
                return Service.NO_REPLY

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

        return Service.NO_REPLY


class Service(object):
    #: Sentinel object to suppress reply generation, since returning ``None``
    #: will trigger a response message containing the pickled ``None``.
    NO_REPLY = object()

    invoker_class = Invoker

    @classmethod
    def name(cls):
        return '%s.%s' % (cls.__module__, cls.__name__)

    def __init__(self, router):
        self.router = router
        self.select = mitogen.select.Select()

    def __repr__(self):
        return '%s()' % (self.__class__.__name__,)

    def on_message(self, recv, msg):
        """
        Called when a message arrives on any of :attr:`select`'s registered
        receivers.
        """

    def on_shutdown(self):
        """
        Called by Pool.shutdown() once the last worker thread has exitted.
        """


class Pool(object):
    """
    Manage a pool of at least one thread that will be used to process messages
    for a collection of services.

    Internally this is implemented by subscribing every :py:class:`Service`'s
    :py:class:`mitogen.core.Receiver` using a single
    :py:class:`mitogen.select.Select`, then arranging for every thread to
    consume messages delivered to that select.

    In this way the threads are fairly shared by all available services, and no
    resources are dedicated to a single idle service.

    There is no penalty for exposing large numbers of services; the list of
    exposed services could even be generated dynamically in response to your
    program's configuration or its input data.

    :param mitogen.core.Router router:
        Router to listen for ``CALL_SERVICE`` messages on.
    :param list services:
        Initial list of services to register.
    """
    activator_class = Activator

    def __init__(self, router, services, size=1):
        self.router = router
        self._activator = self.activator_class()
        self._receiver = mitogen.core.Receiver(
            router=router,
            handle=mitogen.core.CALL_SERVICE,
        )

        self._select = mitogen.select.Select(oneshot=False)
        self._select.add(self._receiver)
        #: Serialize service construction.
        self._lock = threading.Lock()
        self._func_by_recv = {self._receiver: self._on_service_call}
        self._invoker_by_name = {}

        for service in services:
            self.add(service)
        self._threads = []
        for x in range(size):
            thread = threading.Thread(
                name='mitogen.service.Pool.%x.worker-%d' % (id(self), x,),
                target=self._worker_main,
            )
            thread.start()
            self._threads.append(thread)

    @property
    def size(self):
        return len(self._threads)

    def add(self, service):
        name = service.name()
        if name in self._invoker_by_name:
            raise Error('service named %r already registered' % (name,))
        assert service.select not in self._func_by_recv
        invoker = service.invoker_class(service)
        self._invoker_by_name[name] = invoker
        self._func_by_recv[service.select] = service.on_message

    closed = False

    def stop(self):
        self.closed = True
        self._select.close()
        for th in self._threads:
            th.join()
        for invoker in self._invoker_by_name.itervalues():
            invoker.service.on_shutdown()

    def get_invoker(self, name, msg):
        self._lock.acquire()
        try:
            invoker = self._invoker_by_name.get(name)
            if not invoker:
                service = self._activator.activate(self, name, msg)
                invoker = service.invoker_class(service)
                self._invoker_by_name[name] = invoker
        finally:
            self._lock.release()

        return invoker

    def _validate(self, msg):
        tup = msg.unpickle(throw=False)
        if not (isinstance(tup, tuple) and
                len(tup) == 3 and
                isinstance(tup[0], basestring) and
                isinstance(tup[1], basestring) and
                isinstance(tup[2], dict)):
            raise mitogen.core.CallError('Invalid message format.')

    def _on_service_call(self, recv, msg):
        self._validate(msg)
        service_name, method_name, kwargs = msg.unpickle()
        try:
            invoker = self.get_invoker(service_name, msg)
            return invoker.invoke(method_name, kwargs, msg)
        except mitogen.core.CallError:
            e = sys.exc_info()[1]
            LOG.warning('%r: call error: %s: %s', self, msg, e)
            msg.reply(e)
        except Exception:
            LOG.exception('While invoking %r._invoke()', self)
            e = sys.exc_info()[1]
            msg.reply(mitogen.core.CallError(e))

    def _worker_run(self):
        while not self.closed:
            try:
                msg = self._select.get()
            except (mitogen.core.ChannelError, mitogen.core.LatchError):
                e = sys.exc_info()[1]
                LOG.info('%r: channel or latch closed, exitting: %s', self, e)
                return

            func = self._func_by_recv[msg.receiver]
            try:
                func(msg.receiver, msg)
            except Exception:
                LOG.exception('While handling %r using %r', msg, func)

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
            len(self._threads),
            th.name,
        )
