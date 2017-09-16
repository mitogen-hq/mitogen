
import unittest
import mitogen.core
import mitogen.master


class CrazyType(object):
    pass


def function_that_fails():
    raise ValueError('exception text')


def func_with_bad_return_value():
    return CrazyType()


def func_returns_dead():
    return mitogen.core._DEAD


class CallFunctionTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        super(CallFunctionTest, cls).setUpClass()
        cls.broker = mitogen.master.Broker()
        cls.router = mitogen.master.Router(cls.broker)
        cls.local = cls.router.local()

    @classmethod
    def tearDownClass(cls):
        super(CallFunctionTest, cls).tearDownClass()
        cls.broker.shutdown()
        cls.broker.join()

    def test_call_crashes(self):
        try:
            self.local.call(function_that_fails)
            assert 0, 'call didnt fail'
        except mitogen.core.CallError, e:
            pass

        s = str(e)
        etype, _, s = s.partition(': ')
        assert etype == 'exceptions.ValueError'

        msg, _, s = s.partition('\n')
        assert msg == 'exception text'

        # Traceback
        assert len(s) > 0

    def test_bad_return_value(self):
        try:
            self.local.call(func_with_bad_return_value)
            assert 0, 'call didnt fail'
        except mitogen.core.StreamError, e:
            pass

        assert e[0] == (
            "attempted to unpickle 'CrazyType' "
            "in module 'call_function_test'"
        )

    def test_call_returns_dead(self):
        assert mitogen.core._DEAD == self.local.call(func_returns_dead)
