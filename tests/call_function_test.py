import logging
import time

import unittest2

import mitogen.core
import mitogen.master

import testlib


class MyError(Exception):
    pass


class CrazyType(object):
    pass


def function_that_adds_numbers(x, y):
    return x + y


def function_that_fails():
    raise MyError('exception text')


def func_with_bad_return_value():
    return CrazyType()


def func_accepts_returns_context(context):
    return context


def func_accepts_returns_sender(sender):
    sender.send(123)
    sender.close()
    return sender


class CallFunctionTest(testlib.RouterMixin, testlib.TestCase):
    def setUp(self):
        super(CallFunctionTest, self).setUp()
        self.local = self.router.fork()

    def test_succeeds(self):
        self.assertEqual(3, self.local.call(function_that_adds_numbers, 1, 2))

    def test_crashes(self):
        exc = self.assertRaises(mitogen.core.CallError,
            lambda: self.local.call(function_that_fails))

        s = str(exc)
        etype, _, s = s.partition(': ')
        self.assertEqual(etype, '__main__.MyError')

        msg, _, s = s.partition('\n')
        self.assertEqual(msg, 'exception text')

        # Traceback
        self.assertGreater(len(s), 0)

    def test_bad_return_value(self):
        exc = self.assertRaises(mitogen.core.StreamError,
            lambda: self.local.call(func_with_bad_return_value))
        self.assertEquals(
                exc.args[0],
                "cannot unpickle '%s'/'CrazyType'" % (__name__,),
        )

    def test_aborted_on_local_context_disconnect(self):
        stream = self.router._stream_by_id[self.local.context_id]
        self.broker.stop_receive(stream)
        recv = self.local.call_async(time.sleep, 120)
        self.broker.defer(stream.on_disconnect, self.broker)
        exc = self.assertRaises(mitogen.core.ChannelError,
            lambda: recv.get())
        self.assertEquals(exc.args[0], mitogen.core.ChannelError.local_msg)

    def test_aborted_on_local_broker_shutdown(self):
        stream = self.router._stream_by_id[self.local.context_id]
        recv = self.local.call_async(time.sleep, 120)
        time.sleep(0.05)  # Ensure GIL is released
        self.broker.shutdown()
        exc = self.assertRaises(mitogen.core.ChannelError,
            lambda: recv.get())
        self.assertEquals(exc.args[0], mitogen.core.ChannelError.local_msg)

    def test_accepts_returns_context(self):
        context = self.local.call(func_accepts_returns_context, self.local)
        self.assertIsNot(context, self.local)
        self.assertEqual(context.context_id, self.local.context_id)
        self.assertEqual(context.name, self.local.name)

    def test_accepts_returns_sender(self):
        recv = mitogen.core.Receiver(self.router)
        sender = recv.to_sender()
        sender2 = self.local.call(func_accepts_returns_sender, sender)
        self.assertEquals(sender.context.context_id,
                          sender2.context.context_id)
        self.assertEquals(sender.dst_handle, sender2.dst_handle)
        self.assertEquals(123, recv.get().unpickle())
        self.assertRaises(mitogen.core.ChannelError,
                          lambda: recv.get().unpickle())


if __name__ == '__main__':
    unittest2.main()
