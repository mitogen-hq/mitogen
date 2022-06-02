import os
import signal
import sys
import tempfile
import threading
import time

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
        self.assertEqual(mitogen.parent.BROKER_SHUTDOWN_MSG, exc.args[0])


@mitogen.core.takes_econtext
def do_detach(econtext):
    econtext.detach()
    while 1:
        time.sleep(1)
        logging.getLogger('mitogen').error('hi')


class DetachReapTest(testlib.RouterMixin, testlib.TestCase):
    def test_subprocess_preserved_on_shutdown(self):
        c1 = self.router.local()
        pid = c1.call(os.getpid)

        l = mitogen.core.Latch()
        mitogen.core.listen(c1, 'disconnect', l.put)
        c1.call_no_reply(do_detach)
        l.get()

        self.broker.shutdown()
        self.broker.join()

        os.kill(pid, 0)  # succeeds if process still alive

        # now clean up
        os.kill(pid, signal.SIGTERM)
        os.waitpid(pid, 0)
