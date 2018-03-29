import Queue
import StringIO
import logging
import subprocess
import time

import unittest2

import testlib
import mitogen.master
import mitogen.utils


@mitogen.core.takes_router
def return_router_max_message_size(router):
    return router.max_message_size


def send_n_sized_reply(sender, n):
    sender.send(' ' * n)
    return 123


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
