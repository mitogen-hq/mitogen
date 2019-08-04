
import time
import tempfile
import sys
import os
import threading

import unittest2
import testlib

import mitogen.core
import mitogen.parent


class ConnectionTest(testlib.RouterMixin, testlib.TestCase):
    def test_broker_shutdown_while_connect_in_progress(self):
        # if Broker.shutdown() is called while a connection attempt is in
        # progress, the connection should be torn down.

        path = tempfile.mktemp(prefix='broker_shutdown_sem_')
        open(path, 'wb').close()

        os.environ['BROKER_SHUTDOWN_SEMAPHORE'] = path
        result = []

        def thread():
            python_path = testlib.data_path('broker_shutdown_test_python.py')
            try:
                result.append(self.router.local(python_path=python_path))
            except Exception:
                result.append(sys.exc_info()[1])

        th = threading.Thread(target=thread)
        th.start()

        while os.path.exists(path):
            time.sleep(0.05)

        self.broker.shutdown()
        th.join()

        exc, = result
        self.assertTrue(isinstance(exc, mitogen.parent.CancelledError))
        self.assertEquals(mitogen.parent.BROKER_SHUTDOWN_MSG, exc.args[0])


if __name__ == '__main__':
    unittest2.main()
