#!/usr/bin/env python

import unittest2

import mitogen.master
import mitogen.utils


def func0(router):
    return router


@mitogen.utils.with_router
def func(router):
    return router


class RunWithRouterTest(unittest2.TestCase):
    # test_shutdown_on_exception
    # test_shutdown_on_success

    def test_run_with_broker(self):
        router = mitogen.utils.run_with_router(func0)
        self.assertIsInstance(router, mitogen.master.Router)
        self.assertFalse(router.broker._thread.isAlive())


class WithRouterTest(unittest2.TestCase):
    def test_with_broker(self):
        router = func()
        self.assertIsInstance(router, mitogen.master.Router)
        self.assertFalse(router.broker._thread.isAlive())


if __name__ == '__main__':
    unittest2.main()
