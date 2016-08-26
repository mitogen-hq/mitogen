#!/usr/bin/env python

import unittest

import econtext.master
import econtext.utils


def func0(broker):
    return broker


@econtext.utils.with_broker
def func(broker):
    return broker


class RunWithBrokerTest(unittest.TestCase):
    # test_shutdown_on_exception
    # test_shutdown_on_success

    def test_run_with_broker(self):
        broker = econtext.utils.run_with_broker(func0)
        self.assertTrue(isinstance(broker, econtext.master.Broker))
        self.assertFalse(broker._thread.isAlive())


class WithBrokerTest(unittest.TestCase):
    def test_with_broker(self):
        broker = func()
        self.assertTrue(isinstance(broker, econtext.master.Broker))
        self.assertFalse(broker._thread.isAlive())
