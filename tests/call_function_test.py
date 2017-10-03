import logging
import unittest

import mitogen.core
import mitogen.master

import testlib


class CrazyType(object):
    pass


def function_that_adds_numbers(x, y):
    return x + y


def function_that_fails():
    raise ValueError('exception text')


def func_with_bad_return_value():
    return CrazyType()


def func_returns_dead():
    return mitogen.core._DEAD


def func_accepts_returns_context(context):
    return context


class CallFunctionTest(testlib.RouterMixin, testlib.TestCase):
    def setUp(self):
        super(CallFunctionTest, self).setUp()
        self.local = self.router.local()

    def test_succeeds(self):
        assert 3 == self.local.call(function_that_adds_numbers, 1, 2)

    def test_crashes(self):
        exc = self.assertRaises(mitogen.core.CallError,
            lambda: self.local.call(function_that_fails))

        s = str(exc)
        etype, _, s = s.partition(': ')
        assert etype == 'exceptions.ValueError'

        msg, _, s = s.partition('\n')
        assert msg == 'exception text'

        # Traceback
        assert len(s) > 0

    def test_bad_return_value(self):
        exc = self.assertRaises(mitogen.core.StreamError,
            lambda: self.local.call(func_with_bad_return_value))
        self.assertEquals(exc[0], "cannot unpickle '__main__'/'CrazyType'")

    def test_returns_dead(self):
        assert mitogen.core._DEAD == self.local.call(func_returns_dead)

    def test_aborted_on_local_context_disconnect(self):
        stream = self.router._stream_by_id[self.local.context_id]
        self.broker.stop_receive(stream)
        recv = self.local.call_async(time.sleep, 120)
        self.broker.defer(stream.on_disconnect, self.broker)
        exc = self.assertRaises(mitogen.core.ChannelError,
            lambda: recv.get())
        self.assertEquals(exc[0], mitogen.core.ChannelError.local_msg)

    def test_aborted_on_local_broker_shutdown(self):
        assert 0, 'todo'

    def test_accepts_returns_context(self):
        context = self.local.call(func_accepts_returns_context, self.local)
        assert context is not self.local
        assert context.context_id == self.local.context_id
        assert context.name == self.local.name


if __name__ == '__main__':
    unittest.main()
