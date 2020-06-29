
import logging
import mock
import sys

import unittest2
import testlib
import mitogen.core
import mitogen.master
import mitogen.parent
import mitogen.utils
from mitogen.core import b


def ping():
    pass


class BufferingTest(testlib.TestCase):
    klass = mitogen.core.LogHandler

    def record(self):
        return logging.LogRecord(
            name='name',
            level=99,
            pathname='pathname',
            lineno=123,
            msg='msg',
            args=(),
            exc_info=None,
        )

    def build(self):
        context = mock.Mock()
        return context, self.klass(context)

    def test_initially_buffered(self):
        context, handler = self.build()
        rec = self.record()
        handler.emit(rec)
        self.assertEquals(0, context.send.call_count)
        self.assertEquals(1, len(handler._buffer))

    def test_uncork(self):
        context, handler = self.build()
        rec = self.record()
        handler.emit(rec)
        handler.uncork()

        self.assertEquals(1, context.send.call_count)
        self.assertEquals(None, handler._buffer)

        _, args, _ = context.send.mock_calls[0]
        msg, = args

        self.assertEquals(mitogen.core.FORWARD_LOG, msg.handle)
        self.assertEquals(b('name\x0099\x00msg'), msg.data)


class StartupTest(testlib.RouterMixin, testlib.TestCase):
    def test_earliest_messages_logged(self):
        log = testlib.LogCapturer()
        log.start()

        c1 = self.router.local()
        c1.shutdown(wait=True)

        logs = log.stop()
        self.assertTrue('Python version is' in logs)
        self.assertTrue('Parent is context 0 (master)' in logs)

    def test_earliest_messages_logged_via(self):
        c1 = self.router.local(name='c1')
        # ensure any c1-related msgs are processed before beginning capture
        c1.call(ping)

        log = testlib.LogCapturer()
        log.start()

        c2 = self.router.local(via=c1, name='c2', debug=True)
        c2.shutdown(wait=True)

        logs = log.stop()
        self.assertTrue('Python version is' in logs)

        expect = 'Parent is context %s (%s)' % (c1.context_id, 'parent')
        self.assertTrue(expect in logs)

StartupTest = unittest2.skipIf(
    condition=sys.version_info < (2, 7) or sys.version_info >= (3, 6),
    reason="Message log flaky on Python < 2.7 or >= 3.6"
)(StartupTest)


if __name__ == '__main__':
    unittest2.main()
