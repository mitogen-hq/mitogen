
import os
import tempfile
import time
import unittest2

import mitogen.parent


class TtyCreateChildTest(unittest2.TestCase):
    func = staticmethod(mitogen.parent.tty_create_child)

    def test_dev_tty_open_succeeds(self):
        import logging
        logging.basicConfig(level=logging.DEBUG)
        tf = tempfile.NamedTemporaryFile()
        try:
            pid, fd = self.func(
                'bash', '-c', 'exec 2>%s; echo hi > /dev/tty' % (tf.name,)
            )
            # TODO: this waitpid hangs on OS X. Installing a SIGCHLD handler
            # reveals the parent /is/ notified of the child's death, but
            # calling waitpid() from within SIGCHLD yields "No such processes".
            # Meanwhile, even inserting a sleep, the following call will hang.
            waited_pid, status = os.waitpid(pid, 0)
            self.assertEquals(pid, waited_pid)
            self.assertEquals(0, status)
            self.assertEquals('', tf.read())
        finally:
            tf.close()


if __name__ == '__main__':
    unittest2.main()
