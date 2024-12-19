try:
    from unittest import mock
except ImportError:
    import mock

import testlib

import mitogen.core


class ShutdownTest(testlib.TestCase):
    klass = mitogen.core.Broker

    def test_poller_closed(self):
        broker = self.klass()
        actual_close = broker.poller.close
        broker.poller.close = mock.Mock()
        broker.shutdown()
        broker.join()
        self.assertEqual(1, len(broker.poller.close.mock_calls))
        actual_close()


class DeferTest(testlib.TestCase):
    klass = mitogen.core.Broker

    def test_defer(self):
        latch = mitogen.core.Latch()
        broker = self.klass()
        try:
            broker.defer(lambda: latch.put(123))
            self.assertEqual(123, latch.get())
        finally:
            broker.shutdown()
            broker.join()

    def test_defer_after_shutdown(self):
        latch = mitogen.core.Latch()
        broker = self.klass()
        broker.shutdown()
        broker.join()

        e = self.assertRaises(mitogen.core.Error,
            lambda: broker.defer(lambda: latch.put(123)))
        self.assertEqual(e.args[0], mitogen.core.Waker.broker_shutdown_msg)


class DeferSyncTest(testlib.TestCase):
    klass = mitogen.core.Broker

    def test_okay(self):
        broker = self.klass()
        try:
            th = broker.defer_sync(lambda: mitogen.core.threading__current_thread())
            self.assertEqual(th, broker._thread)
        finally:
            broker.shutdown()
            broker.join()

    def test_exception(self):
        broker = self.klass()
        try:
            self.assertRaises(ValueError,
                broker.defer_sync, lambda: int('dave'))
        finally:
            broker.shutdown()
            broker.join()
