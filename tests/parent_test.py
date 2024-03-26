import errno
import fcntl
import os
import signal
import sys
import time
import unittest

try:
    from unittest import mock
except ImportError:
    import mock
import testlib

import mitogen.core
import mitogen.parent

try:
    file
except NameError:
    from io import FileIO as file


def wait_for_child(pid, timeout=1.0):
    deadline = mitogen.core.now() + timeout
    while timeout < mitogen.core.now():
        try:
            target_pid, status = os.waitpid(pid, os.WNOHANG)
            if target_pid == pid:
                return
        except OSError:
            e = sys.exc_info()[1]
            if e.args[0] == errno.ECHILD:
                return

        time.sleep(0.05)

    assert False, "wait_for_child() timed out"


@mitogen.core.takes_econtext
def call_func_in_sibling(ctx, econtext, sync_sender):
    recv = ctx.call_async(time.sleep, 99999)
    sync_sender.send(None)
    recv.get().unpickle()


def wait_for_empty_output_queue(sync_recv, context):
    # wait for sender to submit their RPC. Since the RPC is sent first, the
    # message sent to this sender cannot arrive until we've routed the RPC.
    sync_recv.get()

    router = context.router
    broker = router.broker
    while True:
        # Now wait for the RPC to exit the output queue.
        stream = router.stream_by_id(context.context_id)
        if broker.defer_sync(lambda: stream.protocol.pending_bytes()) == 0:
            return
        time.sleep(0.1)


class GetDefaultRemoteNameTest(testlib.TestCase):
    func = staticmethod(mitogen.parent.get_default_remote_name)

    @mock.patch('os.getpid')
    @mock.patch('getpass.getuser')
    @mock.patch('socket.gethostname')
    def test_slashes(self, mock_gethostname, mock_getuser, mock_getpid):
        # Ensure slashes appearing in the remote name are replaced with
        # underscores.
        mock_gethostname.return_value = 'box'
        mock_getuser.return_value = 'ECORP\\Administrator'
        mock_getpid.return_value = 123
        self.assertEqual("ECORP_Administrator@box:123", self.func())


class ReturncodeToStrTest(testlib.TestCase):
    func = staticmethod(mitogen.parent.returncode_to_str)

    def test_return_zero(self):
        self.assertEqual(self.func(0), 'exited with return code 0')

    def test_return_one(self):
        self.assertEqual(self.func(1), 'exited with return code 1')

    def test_sigkill(self):
        self.assertEqual(self.func(-signal.SIGKILL),
            'exited due to signal %s (SIGKILL)' % (int(signal.SIGKILL),)
        )

    # can't test SIGSTOP without POSIX sessions rabbithole


class ReapChildTest(testlib.RouterMixin, testlib.TestCase):
    def test_connect_timeout(self):
        # Ensure the child process is reaped if the connection times out.
        options = mitogen.parent.Options(
            old_router=self.router,
            max_message_size=self.router.max_message_size,
            python_path=testlib.data_path('python_never_responds.py'),
            connect_timeout=0.5,
        )

        conn = mitogen.parent.Connection(options, router=self.router)
        self.assertRaises(mitogen.core.TimeoutError,
            lambda: conn.connect(context=mitogen.core.Context(None, 1234))
        )
        wait_for_child(conn.proc.pid)
        e = self.assertRaises(OSError,
            lambda: os.kill(conn.proc.pid, 0)
        )
        self.assertEqual(e.args[0], errno.ESRCH)


class StreamErrorTest(testlib.RouterMixin, testlib.TestCase):
    def test_direct_eof(self):
        e = self.assertRaises(mitogen.core.StreamError,
            lambda: self.router.local(
                python_path='true',
                connect_timeout=3,
            )
        )
        prefix = mitogen.parent.Connection.eof_error_msg
        self.assertTrue(e.args[0].startswith(prefix))

    def test_via_eof(self):
        # Verify FD leakage does not keep failed process open.
        local = self.router.local()
        e = self.assertRaises(mitogen.core.StreamError,
            lambda: self.router.local(
                via=local,
                python_path='echo',
                connect_timeout=3,
            )
        )
        expect = mitogen.parent.Connection.eof_error_msg
        self.assertIn(expect, e.args[0])

    def test_direct_enoent(self):
        e = self.assertRaises(mitogen.core.StreamError,
            lambda: self.router.local(
                python_path='derp',
                connect_timeout=3,
            )
        )
        prefix = 'Child start failed: [Errno 2] No such file or directory'
        self.assertTrue(e.args[0].startswith(prefix))

    def test_via_enoent(self):
        local = self.router.local()
        e = self.assertRaises(mitogen.core.StreamError,
            lambda: self.router.local(
                via=local,
                python_path='derp',
                connect_timeout=3,
            )
        )
        s = 'Child start failed: [Errno 2] No such file or directory'
        self.assertIn(s, e.args[0])


class ContextTest(testlib.RouterMixin, testlib.TestCase):
    def test_context_shutdown(self):
        local = self.router.local()
        pid = local.call(os.getpid)
        local.shutdown(wait=True)
        wait_for_child(pid)
        self.assertRaises(OSError, lambda: os.kill(pid, 0))


class OpenPtyTest(testlib.TestCase):
    func = staticmethod(mitogen.parent.openpty)

    def test_pty_returned(self):
        master_fp, slave_fp = self.func()
        try:
            self.assertTrue(master_fp.isatty())
            self.assertIsInstance(master_fp, file)
            self.assertTrue(slave_fp.isatty())
            self.assertIsInstance(slave_fp, file)
        finally:
            master_fp.close()
            slave_fp.close()

    @mock.patch('os.openpty')
    def test_max_reached(self, openpty):
        openpty.side_effect = OSError(errno.ENXIO)
        e = self.assertRaises(mitogen.core.StreamError,
                              lambda: self.func())
        msg = mitogen.parent.OPENPTY_MSG % (openpty.side_effect,)
        self.assertEqual(e.args[0], msg)

    @unittest.skipIf(condition=(os.uname()[0] != 'Linux'),
                      reason='Fallback only supported on Linux')
    @mock.patch('os.openpty')
    def test_broken_linux_fallback(self, openpty):
        openpty.side_effect = OSError(errno.EPERM)
        master_fp, slave_fp = self.func()
        try:
            st = os.fstat(master_fp.fileno())
            self.assertEqual(5, os.major(st.st_rdev))
            flags = fcntl.fcntl(master_fp.fileno(), fcntl.F_GETFL)
            self.assertTrue(flags & os.O_RDWR)

            st = os.fstat(slave_fp.fileno())
            self.assertEqual(136, os.major(st.st_rdev))
            flags = fcntl.fcntl(slave_fp.fileno(), fcntl.F_GETFL)
            self.assertTrue(flags & os.O_RDWR)
        finally:
            master_fp.close()
            slave_fp.close()


class DisconnectTest(testlib.RouterMixin, testlib.TestCase):
    def test_child_disconnected(self):
        # Easy mode: process notices its own directly connected child is
        # disconnected.
        c1 = self.router.local()
        recv = c1.call_async(time.sleep, 9999)
        c1.shutdown(wait=True)
        e = self.assertRaises(mitogen.core.ChannelError,
            lambda: recv.get())
        self.assertEqual(e.args[0], self.router.respondent_disconnect_msg)

    def test_indirect_child_disconnected(self):
        # Achievement unlocked: process notices an indirectly connected child
        # is disconnected.
        c1 = self.router.local()
        c2 = self.router.local(via=c1)
        recv = c2.call_async(time.sleep, 9999)
        c2.shutdown(wait=True)
        e = self.assertRaises(mitogen.core.ChannelError,
            lambda: recv.get())
        self.assertEqual(e.args[0], self.router.respondent_disconnect_msg)

    def test_indirect_child_intermediary_disconnected(self):
        # Battlefield promotion: process notices indirect child disconnected
        # due to an intermediary child disconnecting.
        c1 = self.router.local()
        c2 = self.router.local(via=c1)
        recv = c2.call_async(time.sleep, 9999)
        c1.shutdown(wait=True)
        e = self.assertRaises(mitogen.core.ChannelError,
            lambda: recv.get())
        self.assertEqual(e.args[0], self.router.respondent_disconnect_msg)

    def test_near_sibling_disconnected(self):
        # Hard mode: child notices sibling connected to same parent has
        # disconnected.
        c1 = self.router.local()
        c2 = self.router.local()

        # Let c1 call functions in c2.
        self.router.stream_by_id(c1.context_id).protocol.auth_id = mitogen.context_id
        c1.call(mitogen.parent.upgrade_router)

        sync_recv = mitogen.core.Receiver(self.router)
        recv = c1.call_async(call_func_in_sibling, c2,
            sync_sender=sync_recv.to_sender())

        wait_for_empty_output_queue(sync_recv, c2)
        c2.shutdown(wait=True)

        e = self.assertRaises(mitogen.core.CallError,
            lambda: recv.get().unpickle())
        s = 'mitogen.core.ChannelError: ' + self.router.respondent_disconnect_msg
        self.assertTrue(e.args[0].startswith(s), str(e))

    def test_far_sibling_disconnected(self):
        # God mode: child of child notices child of child of parent has
        # disconnected.
        c1 = self.router.local(name='c1')
        c11 = self.router.local(name='c11', via=c1)

        c2 = self.router.local(name='c2')
        c22 = self.router.local(name='c22', via=c2)

        # Let c1 call functions in c2.
        self.router.stream_by_id(c1.context_id).protocol.auth_id = mitogen.context_id
        c11.call(mitogen.parent.upgrade_router)

        sync_recv = mitogen.core.Receiver(self.router)
        recv = c11.call_async(call_func_in_sibling, c22,
            sync_sender=sync_recv.to_sender())

        wait_for_empty_output_queue(sync_recv, c22)
        c22.shutdown(wait=True)

        e = self.assertRaises(mitogen.core.CallError,
            lambda: recv.get().unpickle())
        s = 'mitogen.core.ChannelError: ' + self.router.respondent_disconnect_msg
        self.assertTrue(e.args[0].startswith(s))
