import socket

import mitogen.core

import testlib

class SocketPairTest(testlib.TestCase):
    def test_socketpair_blocking_unspecified(self):
        "Test that unspecified blocking arg (None) batches socket.socketpair()"
        sk_fp1, sk_fp2 = socket.socketpair()
        mi_fp1, mi_fp2 = mitogen.core.socketpair()

        self.assertEqual(mitogen.core.get_blocking(sk_fp1.fileno()),
                         mitogen.core.get_blocking(mi_fp1.fileno()))
        self.assertEqual(mitogen.core.get_blocking(sk_fp2.fileno()),
                         mitogen.core.get_blocking(mi_fp2.fileno()))
        mi_fp1.close()
        mi_fp2.close()
        sk_fp1.close()
        sk_fp2.close()

    def test_socketpair_blocking_true(self):
        mi_fp1, mi_fp2 = mitogen.core.socketpair(blocking=True)
        self.assertTrue(mitogen.core.get_blocking(mi_fp1.fileno()))
        self.assertTrue(mitogen.core.get_blocking(mi_fp2.fileno()))
        mi_fp1.close()
        mi_fp2.close()

    def test_socketpair_blocking_false(self):
        mi_fp1, mi_fp2 = mitogen.core.socketpair(blocking=False)
        self.assertFalse(mitogen.core.get_blocking(mi_fp1.fileno()))
        self.assertFalse(mitogen.core.get_blocking(mi_fp2.fileno()))
        mi_fp1.close()
        mi_fp2.close()

