import os

import mitogen.core

import testlib

class PipeTest(testlib.TestCase):
    def test_pipe_blocking_unspecified(self):
        "Test that unspecified blocking arg (None) behaves same as os.pipe()"
        os_rfd, os_wfd = os.pipe()
        mi_rfp, mi_wfp = mitogen.core.pipe()

        self.assertEqual(mitogen.core.get_blocking(os_rfd),
                         mitogen.core.get_blocking(mi_rfp.fileno()))
        self.assertEqual(mitogen.core.get_blocking(os_wfd),
                         mitogen.core.get_blocking(mi_wfp.fileno()))
        mi_rfp.close()
        mi_wfp.close()
        os.close(os_rfd)
        os.close(os_wfd)

    def test_pipe_blocking_true(self):
        mi_rfp, mi_wfp = mitogen.core.pipe(blocking=True)
        self.assertTrue(mitogen.core.get_blocking(mi_rfp.fileno()))
        self.assertTrue(mitogen.core.get_blocking(mi_wfp.fileno()))
        mi_rfp.close()
        mi_wfp.close()

    def test_pipe_blocking_false(self):
        mi_rfp, mi_wfp = mitogen.core.pipe(blocking=False)
        self.assertFalse(mitogen.core.get_blocking(mi_rfp.fileno()))
        self.assertFalse(mitogen.core.get_blocking(mi_wfp.fileno()))
        mi_rfp.close()
        mi_wfp.close()

