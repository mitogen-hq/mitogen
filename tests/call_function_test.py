import logging
import time

import unittest2

import mitogen.core
import mitogen.master

import testlib
import plain_old_module


class CrazyType(object):
    pass


def function_that_adds_numbers(x, y):
    return x + y


def function_that_fails(s=''):
    raise plain_old_module.MyError('exception text'+s)


def func_with_bad_return_value():
    return CrazyType()


def func_returns_arg(context):
    return context


def func_accepts_returns_sender(sender):
    sender.send(123)
    sender.close()
    return sender


class TargetClass:

    offset = 100

    @classmethod
    def add_numbers_with_offset(cls, x, y):
        return cls.offset + x + y


class CallFunctionTest(testlib.RouterMixin, testlib.TestCase):

    def setUp(self):
        super(CallFunctionTest, self).setUp()
        self.local = self.router.fork()

    def test_succeeds(self):
        self.assertEqual(3, self.local.call(function_that_adds_numbers, 1, 2))

    def test_succeeds_class_method(self):
        self.assertEqual(
            self.local.call(TargetClass.add_numbers_with_offset, 1, 2),
            103,
        )

    def test_crashes(self):
        exc = self.assertRaises(mitogen.core.CallError,
            lambda: self.local.call(function_that_fails))

        s = str(exc)
        etype, _, s = s.partition(': ')
        self.assertEqual(etype, 'plain_old_module.MyError')

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
        context = self.local.call(func_returns_arg, self.local)
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


class ChainTest(testlib.RouterMixin, testlib.TestCase):
    # Verify mitogen_chain functionality.

    def setUp(self):
        super(ChainTest, self).setUp()
        self.local = self.router.fork()

    def test_subsequent_calls_produce_same_error(self):
        self.assertEquals('xx',
            self.local.call(func_returns_arg, 'xx', mitogen_chain='c1'))
        self.local.call_no_reply(function_that_fails, 'x1', mitogen_chain='c1')
        e1 = self.assertRaises(mitogen.core.CallError,
            lambda: self.local.call(function_that_fails, 'x2', mitogen_chain='c1'))
        e2 = self.assertRaises(mitogen.core.CallError,
            lambda: self.local.call(func_returns_arg, 'x3', mitogen_chain='c1'))
        self.assertEquals(str(e1), str(e2))

    def test_unrelated_overlapping_failed_chains(self):
        self.local.call_no_reply(function_that_fails, 'c1', mitogen_chain='c1')
        self.assertEquals('yes',
            self.local.call(func_returns_arg, 'yes', mitogen_chain='c2'))
        self.assertRaises(mitogen.core.CallError,
            lambda: self.local.call(func_returns_arg, 'yes', mitogen_chain='c1'))
        self.local.call_no_reply(function_that_fails, 'c2', mitogen_chain='c2')

    def test_forget(self):
        self.local.call_no_reply(function_that_fails, 'x1', mitogen_chain='c1')
        e1 = self.assertRaises(mitogen.core.CallError,
            lambda: self.local.call(function_that_fails, 'x2', mitogen_chain='c1'))
        self.local.forget_chain('c1')
        self.assertEquals('x3',
            self.local.call(func_returns_arg, 'x3', mitogen_chain='c1'))


if __name__ == '__main__':
    unittest2.main()
