import signal

import testlib
try:
    from unittest import mock
except ImportError:
    import mock

import mitogen.parent


class ReaperTest(testlib.TestCase):
    @mock.patch('os.kill')
    def test_calc_delay(self, kill):
        broker = mock.Mock()
        proc = mock.Mock()
        proc.poll.return_value = None
        reaper = mitogen.parent.Reaper(broker, proc, True, True)
        self.assertEqual(50, int(1000 * reaper._calc_delay(0)))
        self.assertEqual(86, int(1000 * reaper._calc_delay(1)))
        self.assertEqual(147, int(1000 * reaper._calc_delay(2)))
        self.assertEqual(254, int(1000 * reaper._calc_delay(3)))
        self.assertEqual(437, int(1000 * reaper._calc_delay(4)))
        self.assertEqual(752, int(1000 * reaper._calc_delay(5)))
        self.assertEqual(1294, int(1000 * reaper._calc_delay(6)))

    @mock.patch('os.kill')
    def test_reap_calls(self, kill):
        broker = mock.Mock()
        proc = mock.Mock()
        proc.poll.return_value = None

        reaper = mitogen.parent.Reaper(broker, proc, True, True)

        reaper.reap()
        self.assertEqual(0, kill.call_count)

        reaper.reap()
        self.assertEqual(1, kill.call_count)

        reaper.reap()
        reaper.reap()
        reaper.reap()
        self.assertEqual(1, kill.call_count)

        reaper.reap()
        self.assertEqual(2, kill.call_count)

        self.assertEqual(kill.mock_calls, [
            mock.call(proc.pid, signal.SIGTERM),
            mock.call(proc.pid, signal.SIGKILL),
        ])
