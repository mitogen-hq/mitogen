
import signal
import unittest2
import testlib
import mock

import mitogen.parent


class ReaperTest(testlib.TestCase):
    @mock.patch('os.kill')
    def test_calc_delay(self, kill):
        broker = mock.Mock()
        proc = mock.Mock()
        proc.poll.return_value = None
        reaper = mitogen.parent.Reaper(broker, proc, True, True)
        self.assertEquals(50, int(1000 * reaper._calc_delay(0)))
        self.assertEquals(86, int(1000 * reaper._calc_delay(1)))
        self.assertEquals(147, int(1000 * reaper._calc_delay(2)))
        self.assertEquals(254, int(1000 * reaper._calc_delay(3)))
        self.assertEquals(437, int(1000 * reaper._calc_delay(4)))
        self.assertEquals(752, int(1000 * reaper._calc_delay(5)))
        self.assertEquals(1294, int(1000 * reaper._calc_delay(6)))

    @mock.patch('os.kill')
    def test_reap_calls(self, kill):
        broker = mock.Mock()
        proc = mock.Mock()
        proc.poll.return_value = None

        reaper = mitogen.parent.Reaper(broker, proc, True, True)

        reaper.reap()
        self.assertEquals(0, kill.call_count)

        reaper.reap()
        self.assertEquals(1, kill.call_count)

        reaper.reap()
        reaper.reap()
        reaper.reap()
        self.assertEquals(1, kill.call_count)

        reaper.reap()
        self.assertEquals(2, kill.call_count)

        self.assertEquals(kill.mock_calls, [
            mock.call(proc.pid, signal.SIGTERM),
            mock.call(proc.pid, signal.SIGKILL),
        ])


if __name__ == '__main__':
    unittest2.main()
