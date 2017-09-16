#!/usr/bin/env python

import socket
import time
import unittest

import mitogen.master
import mitogen.utils


@mitogen.utils.with_broker
def do_stuff(broker):
    context = mitogen.master.connect(broker)
    t0 = time.time()
    ncalls = 1000
    for x in xrange(ncalls):
        context.call(socket.gethostname)
    return (1e6 * (time.time() - t0)) / ncalls


class LocalContextTimingTest(unittest.TestCase):
    def test_timing(self):
        self.assertLess(do_stuff(), 1000)
