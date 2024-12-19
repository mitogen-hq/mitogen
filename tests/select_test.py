import mitogen.core
import mitogen.select

import testlib


class BoolTest(testlib.RouterMixin, testlib.TestCase):
    klass = mitogen.select.Select

    def test_latch(self):
        latch = mitogen.core.Latch()  # oneshot
        select = self.klass()
        self.assertFalse(select)
        select.add(latch)
        self.assertTrue(select)

        latch.put(123)
        self.assertTrue(select)
        self.assertEqual(123, select.get())
        self.assertFalse(select)

    def test_receiver(self):
        recv = mitogen.core.Receiver(self.router)  # oneshot
        select = self.klass()
        self.assertFalse(select)
        select.add(recv)
        self.assertTrue(select)

        recv._on_receive(mitogen.core.Message.pickled('123'))
        self.assertTrue(select)
        self.assertEqual('123', select.get().unpickle())
        self.assertFalse(select)


class AddTest(testlib.RouterMixin, testlib.TestCase):
    klass = mitogen.select.Select

    def test_latch(self):
        latch = mitogen.core.Latch()
        select = self.klass()
        select.add(latch)
        self.assertEqual(1, len(select._receivers))
        self.assertEqual(latch, select._receivers[0])
        self.assertEqual(select._put, latch.notify)

    def test_receiver(self):
        recv = mitogen.core.Receiver(self.router)
        select = self.klass()
        select.add(recv)
        self.assertEqual(1, len(select._receivers))
        self.assertEqual(recv, select._receivers[0])
        self.assertEqual(select._put, recv.notify)

    def test_channel(self):
        context = self.router.local()
        chan = mitogen.core.Channel(self.router, context, 1234)
        select = self.klass()
        select.add(chan)
        self.assertEqual(1, len(select._receivers))
        self.assertEqual(chan, select._receivers[0])
        self.assertEqual(select._put, chan.notify)

    def test_subselect_empty(self):
        select = self.klass()
        subselect = self.klass()
        select.add(subselect)
        self.assertEqual(1, len(select._receivers))
        self.assertEqual(subselect, select._receivers[0])
        self.assertEqual(select._put, subselect.notify)

    def test_subselect_nonempty(self):
        recv = mitogen.core.Receiver(self.router)
        select = self.klass()
        subselect = self.klass()
        subselect.add(recv)

        select.add(subselect)
        self.assertEqual(1, len(select._receivers))
        self.assertEqual(subselect, select._receivers[0])
        self.assertEqual(select._put, subselect.notify)

    def test_subselect_loop_direct(self):
        select = self.klass()
        exc = self.assertRaises(mitogen.select.Error,
            lambda: select.add(select))
        self.assertEqual(str(exc), self.klass.loop_msg)

    def test_subselect_loop_indirect(self):
        s0 = self.klass()
        s1 = self.klass()
        s2 = self.klass()

        s0.add(s1)
        s1.add(s2)
        exc = self.assertRaises(mitogen.select.Error,
            lambda: s2.add(s0))
        self.assertEqual(str(exc), self.klass.loop_msg)

    def test_double_add_receiver(self):
        select = self.klass()
        recv = mitogen.core.Receiver(self.router)
        select.add(recv)
        exc = self.assertRaises(mitogen.select.Error,
            lambda: select.add(recv))
        self.assertEqual(str(exc), self.klass.owned_msg)

    def test_double_add_subselect(self):
        select = self.klass()
        select2 = self.klass()
        select.add(select2)
        exc = self.assertRaises(mitogen.select.Error,
            lambda: select.add(select2))
        self.assertEqual(str(exc), self.klass.owned_msg)


class RemoveTest(testlib.RouterMixin, testlib.TestCase):
    klass = mitogen.select.Select

    def test_receiver_empty(self):
        select = self.klass()
        recv = mitogen.core.Receiver(self.router)
        exc = self.assertRaises(mitogen.select.Error,
            lambda: select.remove(recv))
        self.assertEqual(str(exc), self.klass.not_present_msg)

    def test_receiver_absent(self):
        select = self.klass()
        recv = mitogen.core.Receiver(self.router)
        recv2 = mitogen.core.Receiver(self.router)
        select.add(recv2)
        exc = self.assertRaises(mitogen.select.Error,
            lambda: select.remove(recv))
        self.assertEqual(str(exc), self.klass.not_present_msg)

    def test_receiver_present(self):
        select = self.klass()
        recv = mitogen.core.Receiver(self.router)
        select.add(recv)
        select.remove(recv)
        self.assertEqual(0, len(select._receivers))
        self.assertEqual(None, recv.notify)

    def test_latch_empty(self):
        select = self.klass()
        latch = mitogen.core.Latch()
        exc = self.assertRaises(mitogen.select.Error,
            lambda: select.remove(latch))
        self.assertEqual(str(exc), self.klass.not_present_msg)

    def test_latch_absent(self):
        select = self.klass()
        latch = mitogen.core.Latch()
        latch2 = mitogen.core.Latch()
        select.add(latch2)
        exc = self.assertRaises(mitogen.select.Error,
            lambda: select.remove(latch))
        self.assertEqual(str(exc), self.klass.not_present_msg)

    def test_latch_present(self):
        select = self.klass()
        latch = mitogen.core.Latch()
        select.add(latch)
        select.remove(latch)
        self.assertEqual(0, len(select._receivers))
        self.assertEqual(None, latch.notify)


class CloseTest(testlib.RouterMixin, testlib.TestCase):
    klass = mitogen.select.Select

    def test_empty(self):
        select = self.klass()
        select.close()  # No effect.

    def test_one_latch(self):
        select = self.klass()
        latch = mitogen.core.Latch()
        select.add(latch)

        self.assertEqual(1, len(select._receivers))
        self.assertEqual(select._put, latch.notify)

        select.close()
        self.assertEqual(0, len(select._receivers))
        self.assertEqual(None, latch.notify)

    def test_one_receiver(self):
        select = self.klass()
        recv = mitogen.core.Receiver(self.router)
        select.add(recv)

        self.assertEqual(1, len(select._receivers))
        self.assertEqual(select._put, recv.notify)

        select.close()
        self.assertEqual(0, len(select._receivers))
        self.assertEqual(None, recv.notify)

    def test_one_subselect(self):
        select = self.klass()
        subselect = self.klass()
        select.add(subselect)

        recv = mitogen.core.Receiver(self.router)
        subselect.add(recv)

        self.assertEqual(1, len(select._receivers))
        self.assertEqual(subselect._put, recv.notify)

        select.close()

        self.assertEqual(0, len(select._receivers))
        self.assertEqual(subselect._put, recv.notify)

        subselect.close()
        self.assertEqual(None, recv.notify)


class EmptyTest(testlib.RouterMixin, testlib.TestCase):
    klass = mitogen.select.Select

    def test_no_receivers(self):
        select = self.klass()
        self.assertTrue(select.empty())

    def test_empty_receiver(self):
        recv = mitogen.core.Receiver(self.router)
        select = self.klass([recv])
        self.assertTrue(select.empty())

    def test_nonempty_receiver_before_add(self):
        recv = mitogen.core.Receiver(self.router)
        recv._on_receive(mitogen.core.Message.pickled('123'))
        select = self.klass([recv])
        self.assertFalse(select.empty())

    def test_nonempty__receiver_after_add(self):
        recv = mitogen.core.Receiver(self.router)
        select = self.klass([recv])
        recv._on_receive(mitogen.core.Message.pickled('123'))
        self.assertFalse(select.empty())

    def test_empty_latch(self):
        latch = mitogen.core.Latch()
        select = self.klass([latch])
        self.assertTrue(select.empty())

    def test_nonempty_latch_before_add(self):
        latch = mitogen.core.Latch()
        latch.put(123)
        select = self.klass([latch])
        self.assertFalse(select.empty())

    def test_nonempty__latch_after_add(self):
        latch = mitogen.core.Latch()
        select = self.klass([latch])
        latch.put(123)
        self.assertFalse(select.empty())


class IterTest(testlib.RouterMixin, testlib.TestCase):
    klass = mitogen.select.Select

    def test_empty(self):
        select = self.klass()
        self.assertEqual([], list(select))

    def test_nonempty_receiver(self):
        recv = mitogen.core.Receiver(self.router)
        select = self.klass([recv])
        msg = mitogen.core.Message.pickled('123')
        recv._on_receive(msg)
        self.assertEqual([msg], list(select))

    def test_nonempty_latch(self):
        latch = mitogen.core.Latch()
        select = self.klass([latch])
        latch.put(123)
        self.assertEqual([123], list(select))


class OneShotTest(testlib.RouterMixin, testlib.TestCase):
    klass = mitogen.select.Select

    def test_true_receiver_removed_after_get(self):
        recv = mitogen.core.Receiver(self.router)
        select = self.klass([recv])
        msg = mitogen.core.Message.pickled('123')
        recv._on_receive(msg)
        msg_ = select.get()
        self.assertEqual(msg, msg_)
        self.assertEqual(0, len(select._receivers))
        self.assertEqual(None, recv.notify)

    def test_false_receiver_persists_after_get(self):
        recv = mitogen.core.Receiver(self.router)
        select = self.klass([recv], oneshot=False)
        msg = mitogen.core.Message.pickled('123')
        recv._on_receive(msg)

        self.assertEqual(msg, select.get())
        self.assertEqual(1, len(select._receivers))
        self.assertEqual(recv, select._receivers[0])
        self.assertEqual(select._put, recv.notify)

    def test_true_latch_removed_after_get(self):
        latch = mitogen.core.Latch()
        select = self.klass([latch])
        latch.put(123)
        self.assertEqual(123, select.get())
        self.assertEqual(0, len(select._receivers))
        self.assertEqual(None, latch.notify)

    def test_false_latch_persists_after_get(self):
        latch = mitogen.core.Latch()
        select = self.klass([latch], oneshot=False)
        latch.put(123)

        self.assertEqual(123, select.get())
        self.assertEqual(1, len(select._receivers))
        self.assertEqual(latch, select._receivers[0])
        self.assertEqual(select._put, latch.notify)


class GetReceiverTest(testlib.RouterMixin, testlib.TestCase):
    klass = mitogen.select.Select

    def test_no_receivers(self):
        select = self.klass()
        exc = self.assertRaises(mitogen.select.Error,
            lambda: select.get())
        self.assertEqual(str(exc), self.klass.empty_msg)

    def test_timeout_no_receivers(self):
        select = self.klass()
        exc = self.assertRaises(mitogen.select.Error,
            lambda: select.get(timeout=1.0))
        self.assertEqual(str(exc), self.klass.empty_msg)

    def test_zero_timeout(self):
        recv = mitogen.core.Receiver(self.router)
        select = self.klass([recv])
        self.assertRaises(mitogen.core.TimeoutError,
            lambda: select.get(timeout=0.0))

    def test_timeout(self):
        recv = mitogen.core.Receiver(self.router)
        select = self.klass([recv])
        self.assertRaises(mitogen.core.TimeoutError,
            lambda: select.get(timeout=0.1))

    def test_nonempty_before_add(self):
        recv = mitogen.core.Receiver(self.router)
        recv._on_receive(mitogen.core.Message.pickled('123'))
        select = self.klass([recv])
        msg = select.get()
        self.assertEqual('123', msg.unpickle())

    def test_nonempty_multiple_items_before_add(self):
        recv = mitogen.core.Receiver(self.router)
        recv._on_receive(mitogen.core.Message.pickled('123'))
        recv._on_receive(mitogen.core.Message.pickled('234'))
        select = self.klass([recv], oneshot=False)
        msg = select.get()
        self.assertEqual('123', msg.unpickle())
        msg = select.get()
        self.assertEqual('234', msg.unpickle())
        self.assertRaises(mitogen.core.TimeoutError,
            lambda: select.get(block=False))

    def test_nonempty_after_add(self):
        recv = mitogen.core.Receiver(self.router)
        select = self.klass([recv])
        recv._on_receive(mitogen.core.Message.pickled('123'))
        msg = select.get()
        self.assertEqual('123', msg.unpickle())

    def test_nonempty_receiver_attr_set(self):
        recv = mitogen.core.Receiver(self.router)
        select = self.klass([recv])
        recv._on_receive(mitogen.core.Message.pickled('123'))
        msg = select.get()
        self.assertEqual(msg.receiver, recv)

    def test_drained_by_other_thread(self):
        recv = mitogen.core.Receiver(self.router)
        recv._on_receive(mitogen.core.Message.pickled('123'))
        select = self.klass([recv])
        msg = recv.get()
        self.assertEqual('123', msg.unpickle())
        self.assertRaises(mitogen.core.TimeoutError,
            lambda: select.get(timeout=0.0))


class GetLatchTest(testlib.RouterMixin, testlib.TestCase):
    klass = mitogen.select.Select

    def test_no_latches(self):
        select = self.klass()
        exc = self.assertRaises(mitogen.select.Error,
            lambda: select.get())
        self.assertEqual(str(exc), self.klass.empty_msg)

    def test_timeout_no_receivers(self):
        select = self.klass()
        exc = self.assertRaises(mitogen.select.Error,
            lambda: select.get(timeout=1.0))
        self.assertEqual(str(exc), self.klass.empty_msg)

    def test_zero_timeout(self):
        latch = mitogen.core.Latch()
        select = self.klass([latch])
        self.assertRaises(mitogen.core.TimeoutError,
            lambda: select.get(timeout=0.0))

    def test_timeout(self):
        latch = mitogen.core.Latch()
        select = self.klass([latch])
        self.assertRaises(mitogen.core.TimeoutError,
            lambda: select.get(timeout=0.1))

    def test_nonempty_before_add(self):
        latch = mitogen.core.Latch()
        latch.put(123)
        select = self.klass([latch])
        self.assertEqual(123, select.get())

    def test_nonempty_multiple_items_before_add(self):
        latch = mitogen.core.Latch()
        latch.put(123)
        latch.put(234)
        select = self.klass([latch], oneshot=False)
        self.assertEqual(123, select.get())
        self.assertEqual(234, select.get())
        self.assertRaises(mitogen.core.TimeoutError,
            lambda: select.get(block=False))

    def test_nonempty_after_add(self):
        latch = mitogen.core.Latch()
        select = self.klass([latch])
        latch.put(123)
        self.assertEqual(123, latch.get())

    def test_drained_by_other_thread(self):
        latch = mitogen.core.Latch()
        latch.put(123)
        select = self.klass([latch])
        self.assertEqual(123, latch.get())
        self.assertRaises(mitogen.core.TimeoutError,
            lambda: select.get(timeout=0.0))


class GetEventTest(testlib.RouterMixin, testlib.TestCase):
    klass = mitogen.select.Select

    def test_empty(self):
        select = self.klass()
        exc = self.assertRaises(mitogen.select.Error,
            lambda: select.get())
        self.assertEqual(str(exc), self.klass.empty_msg)

    def test_latch(self):
        latch = mitogen.core.Latch()
        latch.put(123)
        select = self.klass([latch])
        event = select.get_event()
        self.assertEqual(latch, event.source)
        self.assertEqual(123, event.data)

    def test_receiver(self):
        recv = mitogen.core.Receiver(self.router)
        recv._on_receive(mitogen.core.Message.pickled('123'))
        select = self.klass([recv])
        event = select.get_event()
        self.assertEqual(recv, event.source)
        self.assertEqual('123', event.data.unpickle())
