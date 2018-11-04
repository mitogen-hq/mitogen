
import threading

import mock
import unittest2

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
        self.assertEquals(1, len(broker.poller.close.mock_calls))
        actual_close()


class DeferSyncTest(testlib.TestCase):
    klass = mitogen.core.Broker

    def test_okay(self):
        broker = self.klass()
        try:
            th = broker.defer_sync(lambda: threading.currentThread())
            self.assertEquals(th, broker._thread)
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


if __name__ == '__main__':
    unittest2.main()
