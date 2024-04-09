try:
    from unittest import mock
except ImportError:
    import mock

import mitogen.core
import mitogen.parent

import testlib


class TimerListMixin(object):
    klass = mitogen.parent.TimerList

    def setUp(self):
        self.list = self.klass()


class GetTimeoutTest(TimerListMixin, testlib.TestCase):
    def test_empty(self):
        self.assertEqual(None, self.list.get_timeout())

    def test_one_event(self):
        self.list.schedule(2, lambda: None)
        self.list._now = lambda: 1
        self.assertEqual(1, self.list.get_timeout())

    def test_two_events_same_moment(self):
        self.list.schedule(2, lambda: None)
        self.list.schedule(2, lambda: None)
        self.list._now = lambda: 1
        self.assertEqual(1, self.list.get_timeout())

    def test_two_events(self):
        self.list.schedule(2, lambda: None)
        self.list.schedule(3, lambda: None)
        self.list._now = lambda: 1
        self.assertEqual(1, self.list.get_timeout())

    def test_two_events_expired(self):
        self.list.schedule(2, lambda: None)
        self.list.schedule(3, lambda: None)
        self.list._now = lambda: 3
        self.assertEqual(0, self.list.get_timeout())

    def test_two_events_in_past(self):
        self.list.schedule(2, lambda: None)
        self.list.schedule(3, lambda: None)
        self.list._now = lambda: 30
        self.assertEqual(0, self.list.get_timeout())

    def test_two_events_in_past(self):
        self.list.schedule(2, lambda: None)
        self.list.schedule(3, lambda: None)
        self.list._now = lambda: 30
        self.assertEqual(0, self.list.get_timeout())

    def test_one_cancelled(self):
        t1 = self.list.schedule(2, lambda: None)
        t2 = self.list.schedule(3, lambda: None)
        self.list._now = lambda: 0
        t1.cancel()
        self.assertEqual(3, self.list.get_timeout())

    def test_two_cancelled(self):
        t1 = self.list.schedule(2, lambda: None)
        t2 = self.list.schedule(3, lambda: None)
        self.list._now = lambda: 0
        t1.cancel()
        t2.cancel()
        self.assertEqual(None, self.list.get_timeout())


class ScheduleTest(TimerListMixin, testlib.TestCase):
    def test_in_past(self):
        self.list._now = lambda: 30
        timer = self.list.schedule(29, lambda: None)
        self.assertEqual(29, timer.when)
        self.assertEqual(0, self.list.get_timeout())

    def test_in_future(self):
        self.list._now = lambda: 30
        timer = self.list.schedule(31, lambda: None)
        self.assertEqual(31, timer.when)
        self.assertEqual(1, self.list.get_timeout())

    def test_same_moment(self):
        self.list._now = lambda: 30
        timer = self.list.schedule(31, lambda: None)
        timer2 = self.list.schedule(31, lambda: None)
        self.assertEqual(31, timer.when)
        self.assertEqual(31, timer2.when)
        self.assertIsNot(timer, timer2)
        self.assertEqual(1, self.list.get_timeout())


class ExpireTest(TimerListMixin, testlib.TestCase):
    def test_in_past(self):
        timer = self.list.schedule(29, mock.Mock())
        self.assertTrue(timer.active)
        self.list._now = lambda: 30
        self.list.expire()
        self.assertEqual(1, len(timer.func.mock_calls))
        self.assertFalse(timer.active)

    def test_in_future(self):
        timer = self.list.schedule(29, mock.Mock())
        self.assertTrue(timer.active)
        self.list._now = lambda: 28
        self.list.expire()
        self.assertEqual(0, len(timer.func.mock_calls))
        self.assertTrue(timer.active)

    def test_same_moment(self):
        timer = self.list.schedule(29, mock.Mock())
        timer2 = self.list.schedule(29, mock.Mock())
        self.assertTrue(timer.active)
        self.assertTrue(timer2.active)
        self.list._now = lambda: 29
        self.list.expire()
        self.assertEqual(1, len(timer.func.mock_calls))
        self.assertEqual(1, len(timer2.func.mock_calls))
        self.assertFalse(timer.active)
        self.assertFalse(timer2.active)

    def test_cancelled(self):
        self.list._now = lambda: 29
        timer = self.list.schedule(29, mock.Mock())
        timer.cancel()
        self.assertEqual(None, self.list.get_timeout())
        self.list._now = lambda: 29
        self.list.expire()
        self.assertEqual(0, len(timer.func.mock_calls))
        self.assertEqual(None, self.list.get_timeout())


class CancelTest(TimerListMixin, testlib.TestCase):
    def test_single_cancel(self):
        self.list._now = lambda: 29
        timer = self.list.schedule(29, mock.Mock())
        self.assertTrue(timer.active)
        timer.cancel()
        self.assertFalse(timer.active)
        self.list.expire()
        self.assertEqual(0, len(timer.func.mock_calls))

    def test_double_cancel(self):
        self.list._now = lambda: 29
        timer = self.list.schedule(29, mock.Mock())
        timer.cancel()
        self.assertFalse(timer.active)
        timer.cancel()
        self.assertFalse(timer.active)
        self.list.expire()
        self.assertEqual(0, len(timer.func.mock_calls))


@mitogen.core.takes_econtext
def do_timer_test_econtext(econtext):
    do_timer_test(econtext.broker)


def do_timer_test(broker):
    now = mitogen.core.now()
    latch = mitogen.core.Latch()
    broker.defer(lambda:
        broker.timers.schedule(
            now + 0.250,
            lambda: latch.put('hi'),
        )
    )

    assert 'hi' == latch.get()
    assert mitogen.core.now() > (now + 0.250)


class BrokerTimerTest(testlib.TestCase):
    klass = mitogen.master.Broker

    def test_call_later(self):
        broker = self.klass()
        try:
            do_timer_test(broker)
        finally:
            broker.shutdown()
            broker.join()

    def test_child_upgrade(self):
        router = mitogen.master.Router()
        try:
            c = router.local()
            c.call(mitogen.parent.upgrade_router)
            c.call(do_timer_test_econtext)
        finally:
            router.broker.shutdown()
            router.broker.join()
