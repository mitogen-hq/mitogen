import Queue
import StringIO
import logging
import subprocess
import time

import unittest2

import testlib
import mitogen.master
import mitogen.utils


def ping():
    return True


@mitogen.core.takes_router
def return_router_max_message_size(router):
    return router.max_message_size


def send_n_sized_reply(sender, n):
    sender.send(' ' * n)
    return 123


class SourceVerifyTest(testlib.RouterMixin, unittest2.TestCase):
    def setUp(self):
        super(SourceVerifyTest, self).setUp()
        # Create some children, ping them, and store what their messages look
        # like so we can mess with them later.
        self.child1 = self.router.fork()
        self.child1_msg = self.child1.call_async(ping).get()
        self.child1_stream = self.router._stream_by_id[self.child1.context_id]

        self.child2 = self.router.fork()
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

        self.broker.defer(self.router._async_route,
                          self.child2_msg,
                          stream=self.child1_stream)

        # Wait for IO loop to finish everything above.
        self.sync_with_broker()

        # Ensure message wasn't forwarded.
        self.assertTrue(recv.empty())

        # Ensure error was logged.
        expect = 'bad auth_id: got %d via' % (self.child2_msg.auth_id,)
        self.assertTrue(expect in log.stop())

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


class CrashTest(testlib.BrokerMixin, unittest2.TestCase):
    # This is testing both Broker's ability to crash nicely, and Router's
    # ability to respond to the crash event.
    klass = mitogen.master.Router

    def _naughty(self):
        raise ValueError('eek')

    def test_shutdown(self):
        router = self.klass(self.broker)

        sem = mitogen.core.Latch()
        router.add_handler(sem.put)

        log = testlib.LogCapturer('mitogen')
        log.start()

        # Force a crash and ensure it wakes up.
        self.broker._loop_once = self._naughty
        self.broker.defer(lambda: None)

        # sem should have received _DEAD.
        self.assertEquals(mitogen.core._DEAD, sem.get())

        # Ensure it was logged.
        expect = '_broker_main() crashed'
        self.assertTrue(expect in log.stop())



class AddHandlerTest(unittest2.TestCase):
    klass = mitogen.master.Router

    def test_invoked_at_shutdown(self):
        router = self.klass()
        queue = Queue.Queue()
        handle = router.add_handler(queue.put)
        router.broker.shutdown()
        self.assertEquals(queue.get(timeout=5), mitogen.core._DEAD)


class MessageSizeTest(testlib.BrokerMixin, unittest2.TestCase):
    klass = mitogen.master.Router

    def test_local_exceeded(self):
        router = self.klass(broker=self.broker, max_message_size=4096)
        recv = mitogen.core.Receiver(router)

        logs = testlib.LogCapturer()
        logs.start()

        sem = mitogen.core.Latch()
        router.route(mitogen.core.Message.pickled(' '*8192))
        router.broker.defer(sem.put, ' ')  # wlil always run after _async_route
        sem.get()

        expect = 'message too large (max 4096 bytes)'
        self.assertTrue(expect in logs.stop())

    def test_remote_configured(self):
        router = self.klass(broker=self.broker, max_message_size=4096)
        remote = router.fork()
        size = remote.call(return_router_max_message_size)
        self.assertEquals(size, 4096)

    def test_remote_exceeded(self):
        # Ensure new contexts receive a router with the same value.
        router = self.klass(broker=self.broker, max_message_size=4096)
        recv = mitogen.core.Receiver(router)

        logs = testlib.LogCapturer()
        logs.start()

        remote = router.fork()
        remote.call(send_n_sized_reply, recv.to_sender(), 8192)

        expect = 'message too large (max 4096 bytes)'
        self.assertTrue(expect in logs.stop())


if __name__ == '__main__':
    unittest2.main()
