import testlib

import mitogen.os_fork
import mitogen.service


class CorkTest(testlib.RouterMixin, testlib.TestCase):
    klass = mitogen.os_fork.Corker

    def ping(self, latch):
        latch.put('pong')

    def test_cork_broker(self):
        latch = mitogen.core.Latch()
        self.broker.defer(self.ping, latch)
        self.assertEqual('pong', latch.get())

        corker = self.klass(brokers=(self.broker,))
        corker.cork()

        latch = mitogen.core.Latch()
        self.broker.defer(self.ping, latch)
        self.assertRaises(mitogen.core.TimeoutError,
            lambda: latch.get(timeout=0.5))
        corker.uncork()
        self.assertEqual('pong', latch.get())

    def test_cork_pool(self):
        pool = mitogen.service.Pool(self.router, services=(), size=4)
        try:
            latch = mitogen.core.Latch()
            pool.defer(self.ping, latch)
            self.assertEqual('pong', latch.get())

            corker = self.klass(pools=(pool,))
            corker.cork()

            latch = mitogen.core.Latch()
            pool.defer(self.ping, latch)
            self.assertRaises(mitogen.core.TimeoutError,
                lambda: latch.get(timeout=0.5))
            corker.uncork()
            self.assertEqual('pong', latch.get())
        finally:
            pool.stop(join=True)
