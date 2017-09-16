#!/usr/bin/env python

import unittest

import mitogen.master
import mitogen.utils


def func0(broker):
    return broker


@mitogen.utils.with_broker
def func(broker):
    return broker


class RunWithBrokerTest(unittest.TestCase):
    # test_shutdown_on_exception
    # test_shutdown_on_success

    def test_run_with_broker(self):
        broker = mitogen.utils.run_with_broker(func0)
        self.assertTrue(isinstance(broker, mitogen.master.Broker))
        self.assertFalse(broker._thread.isAlive())


class WithBrokerTest(unittest.TestCase):
    def test_with_broker(self):
        broker = func()
        self.assertTrue(isinstance(broker, mitogen.master.Broker))
        self.assertFalse(broker._thread.isAlive())
