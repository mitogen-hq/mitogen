
import os
import sys
import unittest

import mock

import mitogen.master


DATA_DIR = os.path.join(os.path.dirname(__file__), 'data')
sys.path.append(DATA_DIR)


def set_debug():
    import logging
    logging.getLogger('mitogen').setLevel(logging.DEBUG)


def data_path(suffix):
    return os.path.join(DATA_DIR, suffix)


class BrokerMixin(object):
    broker_class = mitogen.master.Broker

    def setUp(self):
        super(BrokerMixin, self).setUp()
        self.broker = self.broker_class()

    def tearDown(self):
        self.broker.shutdown()
        self.broker.join()
        super(BrokerMixin, self).tearDown()
