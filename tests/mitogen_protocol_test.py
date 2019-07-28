
import unittest2
import mock

import mitogen.core

import testlib


class ReceiveOneTest(testlib.TestCase):
    klass = mitogen.core.MitogenProtocol

    def test_corruption(self):
        broker = mock.Mock()
        router = mock.Mock()
        stream = mock.Mock()

        protocol = self.klass(router, 1)
        protocol.stream = stream

        junk = mitogen.core.b('x') * mitogen.core.Message.HEADER_LEN

        capture = testlib.LogCapturer()
        capture.start()
        protocol.on_receive(broker, junk)
        capture.stop()

        self.assertEquals(1, stream.on_disconnect.call_count)
        expect = self.klass.corrupt_msg % (stream.name, junk)
        self.assertTrue(expect in capture.raw())


if __name__ == '__main__':
    unittest2.main()
