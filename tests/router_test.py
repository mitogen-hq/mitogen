import Queue
import subprocess
import time

import unittest2

import testlib
import mitogen.master
import mitogen.utils

mitogen.utils.log_to_file()

class AddHandlerTest(unittest2.TestCase):
    klass = mitogen.master.Router

    def test_invoked_at_shutdown(self):
        router = self.klass()
        queue = Queue.Queue()
        handle = router.add_handler(queue.put)
        router.broker.shutdown()
        self.assertEquals(queue.get(timeout=5), mitogen.core._DEAD)


if __name__ == '__main__':
    unittest2.main()

