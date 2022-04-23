import errno
import os
import sys
import zlib

import testlib
import mitogen.core
import mitogen.master
import mitogen.parent
import mitogen.utils
from mitogen.core import b

try:
    import Queue
except ImportError:
    import queue as Queue


def ping():
    return True


@mitogen.core.takes_router
def ping_context(other, router):
    other = mitogen.parent.Context(router, other.context_id)
    other.call(ping)


@mitogen.core.takes_router
def return_router_max_message_size(router):
    return router.max_message_size


def send_n_sized_reply(sender, n):
    sender.send(' ' * n)
    return 123


class SourceVerifyTest(testlib.RouterMixin, testlib.TestCase):
    def setUp(self):
        super(SourceVerifyTest, self).setUp()
        # Create some children, ping them, and store what their messages look
        # like so we can mess with them later.
        self.child1 = self.router.local()
        self.child1_msg = self.child1.call_async(ping).get()
        self.child1_stream = self.router._stream_by_id[self.child1.context_id]

        self.child2 = self.router.local()
        self.child2_msg = self.child2.call_async(ping).get()
        self.child2_stream = self.router._stream_by_id[self.child2.context_id]

    def test_bad_auth_id(self):
        # Deliver a message locally from child2, but using child1's stream.
        log = testlib.LogCapturer()
        log.start()

        # Used to ensure the message was dropped rather than routed after the
        # error is logged.
        recv = mitogen.core.Receiver(self.router)
        self.child2_msg.handle = recv.handle

        self.broker.defer_sync(
            lambda: self.router._async_route(
               self.child2_msg,
               in_stream=self.child1_stream
           )
        )

        # Ensure message wasn't forwarded.
        self.assertTrue(recv.empty())

        # Ensure error was logged.
        expect = 'bad auth_id: got %r via' % (self.child2_msg.auth_id,)
        self.assertTrue(expect in log.stop())

    def test_parent_unaware_of_disconnect(self):
        # Parent -> Child A -> Child B. B disconnects concurrent to Parent
        # sending message. Parent does not yet know B has disconnected, A
        # receives message from Parent with Parent's auth_id, for a stream that
        # no longer exists.
        c1 = self.router.local()
        strm = self.router.stream_by_id(c1.context_id)
        recv = mitogen.core.Receiver(self.router)

        self.broker.defer(lambda:
            strm.protocol._send(
                mitogen.core.Message(
                    dst_id=1234,  # nonexistent child
                    handle=1234,
                    src_id=mitogen.context_id,
                    reply_to=recv.handle,
                )
            )
        )

        e = self.assertRaises(mitogen.core.ChannelError,
            lambda: recv.get().unpickle()
        )
        self.assertEqual(e.args[0], self.router.no_route_msg % (
            1234,
            c1.context_id,
        ))

    def test_bad_src_id(self):
        # Deliver a message locally from child2 with the correct auth_id, but
        # the wrong src_id.
        log = testlib.LogCapturer()
        log.start()

        # Used to ensure the message was dropped rather than routed after the
        # error is logged.
        recv = mitogen.core.Receiver(self.router)
        self.child2_msg.handle = recv.handle
        self.child2_msg.src_id = self.child1.context_id

        self.broker.defer(self.router._async_route,
                          self.child2_msg,
                          self.child2_stream)

        # Wait for IO loop to finish everything above.
        self.sync_with_broker()

        # Ensure message wasn't forwarded.
        self.assertTrue(recv.empty())

        # Ensure error was lgoged.
        expect = 'bad src_id: got %d via' % (self.child1_msg.src_id,)
        self.assertTrue(expect in log.stop())


class PolicyTest(testlib.RouterMixin, testlib.TestCase):
    def test_allow_any(self):
        # This guy gets everything.
        recv = mitogen.core.Receiver(self.router)
        recv.to_sender().send(123)
        self.sync_with_broker()
        self.assertFalse(recv.empty())
        self.assertEqual(123, recv.get().unpickle())

    def test_refuse_all(self):
        # Deliver a message locally from child2 with the correct auth_id, but
        # the wrong src_id.
        log = testlib.LogCapturer()
        log.start()

        # This guy never gets anything.
        recv = mitogen.core.Receiver(
            router=self.router,
            policy=(lambda msg, stream: False),
        )

        # This guy becomes the reply_to of our refused message.
        reply_target = mitogen.core.Receiver(self.router)

        # Send the message.
        self.router.route(
            mitogen.core.Message(
                dst_id=mitogen.context_id,
                handle=recv.handle,
                reply_to=reply_target.handle,
            )
        )

        # Wait for IO loop.
        self.sync_with_broker()

        # Verify log.
        self.assertTrue(self.router.refused_msg in log.stop())

        # Verify message was not delivered.
        self.assertTrue(recv.empty())

        # Verify CallError received by reply_to target.
        e = self.assertRaises(mitogen.core.ChannelError,
                              lambda: reply_target.get().unpickle())
        self.assertEqual(e.args[0], self.router.refused_msg)


class CrashTest(testlib.BrokerMixin, testlib.TestCase):
    # This is testing both Broker's ability to crash nicely, and Router's
    # ability to respond to the crash event.
    klass = mitogen.master.Router

    def _naughty(self):
        raise ValueError('eek')

    def test_shutdown(self):
        router = self.klass(self.broker)

        sem = mitogen.core.Latch()
        router.add_handler(sem.put)

        log = testlib.LogCapturer()
        log.start()

        # Force a crash and ensure it wakes up.
        self.broker._loop_once = self._naughty
        self.broker.defer(lambda: None)

        # sem should have received dead message.
        self.assertTrue(sem.get().is_dead)

        # Ensure it was logged.
        expect = 'broker crashed'
        self.assertTrue(expect in log.stop())

        self.broker.join()


class AddHandlerTest(testlib.TestCase):
    klass = mitogen.master.Router

    def test_dead_message_sent_at_shutdown(self):
        router = self.klass()
        queue = Queue.Queue()
        handle = router.add_handler(queue.put)
        router.broker.shutdown()
        self.assertTrue(queue.get(timeout=5).is_dead)
        router.broker.join()

    def test_cannot_double_register(self):
        router = self.klass()
        try:
            router.add_handler((lambda: None), handle=1234)
            e = self.assertRaises(mitogen.core.Error,
                lambda: router.add_handler((lambda: None), handle=1234))
            self.assertEqual(router.duplicate_handle_msg, e.args[0])
            router.del_handler(1234)
        finally:
            router.broker.shutdown()
            router.broker.join()

    def test_can_reregister(self):
        router = self.klass()
        try:
            router.add_handler((lambda: None), handle=1234)
            router.del_handler(1234)
            router.add_handler((lambda: None), handle=1234)
            router.del_handler(1234)
        finally:
            router.broker.shutdown()
            router.broker.join()


class MyselfTest(testlib.RouterMixin, testlib.TestCase):
    def test_myself(self):
        myself = self.router.myself()
        self.assertEqual(myself.context_id, mitogen.context_id)
        # TODO: context should know its own name too.
        self.assertEqual(myself.name, 'self')


class MessageSizeTest(testlib.BrokerMixin, testlib.TestCase):
    klass = mitogen.master.Router

    def test_local_exceeded(self):
        router = self.klass(broker=self.broker, max_message_size=4096)

        logs = testlib.LogCapturer()
        logs.start()

        # Send message and block for one IO loop, so _async_route can run.
        router.route(mitogen.core.Message.pickled(' '*8192))
        router.broker.defer_sync(lambda: None)

        expect = 'message too large (max 4096 bytes)'
        self.assertTrue(expect in logs.stop())

    def test_local_dead_message(self):
        # Local router should generate dead message when reply_to is set.
        router = self.klass(broker=self.broker, max_message_size=4096)

        logs = testlib.LogCapturer()
        logs.start()

        expect = router.too_large_msg % (4096,)

        # Try function call. Receiver should be woken by a dead message sent by
        # router due to message size exceeded.
        child = router.local()
        e = self.assertRaises(mitogen.core.ChannelError,
            lambda: child.call(zlib.crc32, ' '*8192))
        self.assertEqual(e.args[0], expect)

        self.assertTrue(expect in logs.stop())

    def test_remote_dead_message(self):
        # Router should send dead message to original recipient when reply_to
        # is unset.
        router = self.klass(broker=self.broker, max_message_size=4096)

        # Try function call. Receiver should be woken by a dead message sent by
        # router due to message size exceeded.
        child = router.local()
        recv = mitogen.core.Receiver(router)

        recv.to_sender().send(b('x') * 4097)
        e = self.assertRaises(mitogen.core.ChannelError,
            lambda: recv.get().unpickle()
        )
        expect = router.too_large_msg % (4096,)
        self.assertEqual(e.args[0], expect)

    def test_remote_configured(self):
        router = self.klass(broker=self.broker, max_message_size=64*1024)
        remote = router.local()
        size = remote.call(return_router_max_message_size)
        self.assertEqual(size, 64*1024)

    def test_remote_of_remote_configured(self):
        router = self.klass(broker=self.broker, max_message_size=64*1024)
        remote = router.local()
        remote2 = router.local(via=remote)
        size = remote2.call(return_router_max_message_size)
        self.assertEqual(size, 64*1024)

    def test_remote_exceeded(self):
        # Ensure new contexts receive a router with the same value.
        router = self.klass(broker=self.broker, max_message_size=64*1024)
        recv = mitogen.core.Receiver(router)

        logs = testlib.LogCapturer()
        logs.start()
        remote = router.local()
        remote.call(send_n_sized_reply, recv.to_sender(), 128*1024)

        expect = 'message too large (max %d bytes)' % (64*1024,)
        self.assertTrue(expect in logs.stop())


class NoRouteTest(testlib.RouterMixin, testlib.TestCase):
    def test_invalid_handle_returns_dead(self):
        # Verify sending a message to an invalid handle yields a dead message
        # from the target context.
        l1 = self.router.local()
        recv = l1.send_async(mitogen.core.Message(handle=999))
        msg = recv.get(throw_dead=False)
        self.assertEqual(msg.is_dead, True)
        self.assertEqual(msg.src_id, l1.context_id)
        self.assertEqual(msg.data, self.router.invalid_handle_msg.encode())

        recv = l1.send_async(mitogen.core.Message(handle=999))
        e = self.assertRaises(mitogen.core.ChannelError,
                              lambda: recv.get())
        self.assertEqual(e.args[0], self.router.invalid_handle_msg)

    def test_totally_invalid_context_returns_dead(self):
        recv = mitogen.core.Receiver(self.router)
        msg = mitogen.core.Message(
            dst_id=1234,
            handle=1234,
            reply_to=recv.handle,
        )
        self.router.route(msg)
        rmsg = recv.get(throw_dead=False)
        self.assertEqual(rmsg.is_dead, True)
        self.assertEqual(rmsg.src_id, mitogen.context_id)
        self.assertEqual(rmsg.data, (self.router.no_route_msg % (
            1234,
            mitogen.context_id,
        )).encode())

        self.router.route(msg)
        e = self.assertRaises(mitogen.core.ChannelError,
                              lambda: recv.get())
        self.assertEqual(e.args[0], (self.router.no_route_msg % (
            1234,
            mitogen.context_id,
        )))

    def test_previously_alive_context_returns_dead(self):
        l1 = self.router.local()
        l1.shutdown(wait=True)
        recv = mitogen.core.Receiver(self.router)
        msg = mitogen.core.Message(
            dst_id=l1.context_id,
            handle=mitogen.core.CALL_FUNCTION,
            reply_to=recv.handle,
        )
        self.router.route(msg)
        rmsg = recv.get(throw_dead=False)
        self.assertEqual(rmsg.is_dead, True)
        self.assertEqual(rmsg.src_id, mitogen.context_id)
        self.assertEqual(rmsg.data, (self.router.no_route_msg % (
            l1.context_id,
            mitogen.context_id,
        )).encode())

        self.router.route(msg)
        e = self.assertRaises(mitogen.core.ChannelError,
                              lambda: recv.get())
        self.assertEqual(e.args[0], self.router.no_route_msg % (
            l1.context_id,
            mitogen.context_id,
        ))


def test_siblings_cant_talk(router):
    l1 = router.local()
    l2 = router.local()
    logs = testlib.LogCapturer()
    logs.start()

    try:
        l2.call(ping_context, l1)
    except mitogen.core.CallError:
        e = sys.exc_info()[1]

    msg = mitogen.core.Router.unidirectional_msg % (
        l2.context_id,
        l1.context_id,
        mitogen.context_id,
    )
    assert msg in str(e)
    assert 'routing mode prevents forward of ' in logs.stop()


@mitogen.core.takes_econtext
def test_siblings_cant_talk_remote(econtext):
    mitogen.parent.upgrade_router(econtext)
    test_siblings_cant_talk(econtext.router)


class UnidirectionalTest(testlib.RouterMixin, testlib.TestCase):
    def test_siblings_cant_talk_master(self):
        self.router.unidirectional = True
        test_siblings_cant_talk(self.router)

    def test_siblings_cant_talk_parent(self):
        # ensure 'unidirectional' attribute is respected for contexts started
        # by children.
        self.router.unidirectional = True
        parent = self.router.local()
        parent.call(test_siblings_cant_talk_remote)

    def test_auth_id_can_talk(self):
        self.router.unidirectional = True
        # One stream has auth_id stamped to that of the master, so it should be
        # treated like a parent.
        l1 = self.router.local()
        l1s = self.router.stream_by_id(l1.context_id)
        l1s.protocol.auth_id = mitogen.context_id
        l1s.protocol.is_privileged = True

        l2 = self.router.local()
        e = self.assertRaises(mitogen.core.CallError,
                              lambda: l2.call(ping_context, l1))

        msg = 'mitogen.core.ChannelError: %s' % (self.router.refused_msg,)
        self.assertTrue(str(e).startswith(msg))


class EgressIdsTest(testlib.RouterMixin, testlib.TestCase):
    def test_egress_ids_populated(self):
        # Ensure Stream.egress_ids is populated on message reception.
        c1 = self.router.local(name='c1')
        c2 = self.router.local(name='c2')

        c1s = self.router.stream_by_id(c1.context_id)
        try:
            c1.call(ping_context, c2)
        except mitogen.core.CallError:
            # Fails because siblings cant call funcs in each other, but this
            # causes messages to be sent.
            pass

        self.assertEqual(c1s.protocol.egress_ids, set([
            mitogen.context_id,
            c2.context_id,
        ]))


class ShutdownTest(testlib.RouterMixin, testlib.TestCase):
    # 613: tests for all the weird shutdown() variants we ended up with.

    def test_shutdown_wait_false(self):
        l1 = self.router.local()
        pid = l1.call(os.getpid)

        strm = self.router.stream_by_id(l1.context_id)
        exitted = mitogen.core.Latch()

        # It is possible for Process 'exit' signal to fire immediately during
        # processing of Stream 'disconnect' signal, so we must wait for both,
        # otherwise ChannelError below will return 'respondent context has
        # disconnected' rather than 'no route', because RouteMonitor hasn't run
        # yet and the Receiver caught Context 'disconnect' signal instead of a
        # dead message.
        mitogen.core.listen(strm.conn.proc, 'exit', exitted.put)
        mitogen.core.listen(strm, 'disconnect', exitted.put)

        l1.shutdown(wait=False)
        exitted.get()
        exitted.get()

        e = self.assertRaises(OSError,
            lambda: os.waitpid(pid, 0))
        self.assertEqual(e.args[0], errno.ECHILD)

        e = self.assertRaises(mitogen.core.ChannelError,
            lambda: l1.call(os.getpid))
        self.assertEqual(e.args[0], mitogen.core.Router.no_route_msg % (
            l1.context_id,
            mitogen.context_id,
        ))

    def test_shutdown_wait_true(self):
        l1 = self.router.local()
        pid = l1.call(os.getpid)

        conn = self.router.stream_by_id(l1.context_id).conn
        exitted = mitogen.core.Latch()
        mitogen.core.listen(conn.proc, 'exit', exitted.put)

        l1.shutdown(wait=True)
        exitted.get()

        e = self.assertRaises(OSError,
            lambda: os.waitpid(pid, 0))
        self.assertEqual(e.args[0], errno.ECHILD)

        e = self.assertRaises(mitogen.core.ChannelError,
            lambda: l1.call(os.getpid))
        self.assertEqual(e.args[0], mitogen.core.Router.no_route_msg % (
            l1.context_id,
            mitogen.context_id,
        ))

    def test_disconnect_invalid_context(self):
        self.router.disconnect(
            mitogen.core.Context(self.router, 1234)
        )

    def test_disconnect_valid_context(self):
        l1 = self.router.local()
        pid = l1.call(os.getpid)

        strm = self.router.stream_by_id(l1.context_id)

        exitted = mitogen.core.Latch()
        mitogen.core.listen(strm.conn.proc, 'exit', exitted.put)
        self.router.disconnect_stream(strm)
        exitted.get()

        e = self.assertRaises(OSError,
            lambda: os.waitpid(pid, 0))
        self.assertEqual(e.args[0], errno.ECHILD)

        e = self.assertRaises(mitogen.core.ChannelError,
            lambda: l1.call(os.getpid))
        self.assertEqual(e.args[0], mitogen.core.Router.no_route_msg % (
            l1.context_id,
            mitogen.context_id,
        ))

    def test_disconnect_all(self):
        l1 = self.router.local()
        l2 = self.router.local()

        pids = [l1.call(os.getpid), l2.call(os.getpid)]

        exitted = mitogen.core.Latch()
        for ctx in l1, l2:
            strm = self.router.stream_by_id(ctx.context_id)
            mitogen.core.listen(strm.conn.proc, 'exit', exitted.put)

        self.router.disconnect_all()
        exitted.get()
        exitted.get()

        for pid in pids:
            e = self.assertRaises(OSError,
                lambda: os.waitpid(pid, 0))
            self.assertEqual(e.args[0], errno.ECHILD)

        for ctx in l1, l2:
            e = self.assertRaises(mitogen.core.ChannelError,
                lambda: ctx.call(os.getpid))
            self.assertEqual(e.args[0], mitogen.core.Router.no_route_msg % (
                ctx.context_id,
                mitogen.context_id,
            ))
