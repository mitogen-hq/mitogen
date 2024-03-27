import errno
import select

try:
    from unittest import mock
except ImportError:
    import mock

import testlib
import mitogen.core


def py24_mock_fix(m):
    def wrapper(*args, **kwargs):
        ret = m(*args, **kwargs)
        if isinstance(ret, Exception):
            raise ret
        return ret
    return wrapper


class RestartTest(object):
    func = staticmethod(mitogen.core.io_op)
    exception_class = None

    def test_eintr_restarts(self):
        m = mock.Mock()
        m.side_effect = [
            self.exception_class(errno.EINTR),
            self.exception_class(errno.EINTR),
            self.exception_class(errno.EINTR),
            'yay',
        ]
        rc, disconnected = self.func(py24_mock_fix(m), 'input')
        self.assertEqual(rc, 'yay')
        self.assertFalse(disconnected)
        self.assertEqual(4, m.call_count)
        self.assertEqual(m.mock_calls, [
            mock.call('input'),
            mock.call('input'),
            mock.call('input'),
            mock.call('input'),
        ])


class SelectRestartTest(RestartTest, testlib.TestCase):
    exception_class = select.error


class OsErrorRestartTest(RestartTest, testlib.TestCase):
    exception_class = OSError


class DisconnectTest(object):
    func = staticmethod(mitogen.core.io_op)
    errno = None
    exception_class = None

    def test_disconnection(self):
        m = mock.Mock()
        m.side_effect = self.exception_class(self.errno)
        rc, disconnected = self.func(m, 'input')
        self.assertEqual(rc, None)
        self.assertTrue(disconnected)
        self.assertEqual(1, m.call_count)
        self.assertEqual(m.mock_calls, [
            mock.call('input'),
        ])


class SelectDisconnectEioTest(DisconnectTest, testlib.TestCase):
    errno = errno.EIO
    exception_class = select.error


class SelectDisconnectEconnresetTest(DisconnectTest, testlib.TestCase):
    errno = errno.ECONNRESET
    exception_class = select.error


class SelectDisconnectEpipeTest(DisconnectTest, testlib.TestCase):
    errno = errno.EPIPE
    exception_class = select.error


class OsErrorDisconnectEioTest(DisconnectTest, testlib.TestCase):
    errno = errno.EIO
    exception_class = OSError


class OsErrorDisconnectEconnresetTest(DisconnectTest, testlib.TestCase):
    errno = errno.ECONNRESET
    exception_class = OSError


class OsErrorDisconnectEpipeTest(DisconnectTest, testlib.TestCase):
    errno = errno.EPIPE
    exception_class = OSError


class ExceptionTest(object):
    func = staticmethod(mitogen.core.io_op)
    errno = None
    exception_class = None

    def test_exception(self):
        m = mock.Mock()
        m.side_effect = self.exception_class(self.errno)
        e = self.assertRaises(self.exception_class,
                              lambda: self.func(m, 'input'))
        self.assertEqual(e, m.side_effect)
        self.assertEqual(1, m.call_count)
        self.assertEqual(m.mock_calls, [
            mock.call('input'),
        ])


class SelectExceptionTest(ExceptionTest, testlib.TestCase):
    errno = errno.EBADF
    exception_class = select.error


class OsErrorExceptionTest(ExceptionTest, testlib.TestCase):
    errno = errno.EBADF
    exception_class = OSError
