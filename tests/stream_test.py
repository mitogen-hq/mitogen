
import unittest2
import mock

import mitogen.core

import testlib


class ReceiveOneTest(testlib.TestCase):
    klass = mitogen.core.Stream

    def test_corruption(self):
        broker = mock.Mock()
        router = mock.Mock()

        stream = self.klass(router, 1)
        junk = mitogen.core.b('x') * stream.HEADER_LEN
        stream._input_buf = [junk]
        stream._input_buf_len = len(junk)

        capture = testlib.LogCapturer()
        capture.start()
        ret = stream._receive_one(broker)
        #self.assertEquals(1, broker.stop_receive.mock_calls)
        capture.stop()

        self.assertFalse(ret)
        self.assertTrue((self.klass.corrupt_msg % (junk,)) in capture.raw())


if __name__ == '__main__':
    unittest2.main()
