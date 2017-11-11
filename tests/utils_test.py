#!/usr/bin/env python

import unittest2 as unittest

import mitogen.master
import mitogen.utils


def func0(router):
    return router


@mitogen.utils.with_router
def func(router):
    return router


class RunWithRouterTest(unittest.TestCase):
    # test_shutdown_on_exception
    # test_shutdown_on_success

    def test_run_with_broker(self):
        router = mitogen.utils.run_with_router(func0)
        self.assertTrue(isinstance(router, mitogen.master.Router))
        self.assertFalse(router.broker._thread.isAlive())


class WithRouterTest(unittest.TestCase):
    def test_with_broker(self):
        router = func()
        self.assertTrue(isinstance(router, mitogen.master.Router))
        self.assertFalse(router.broker._thread.isAlive())


if __name__ == '__main__':
    unittest.main()
