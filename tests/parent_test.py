import errno
import fcntl
import os
import signal
import subprocess
import sys
import tempfile
import time

import mock
import unittest2
import testlib
from testlib import Popen__terminate

import mitogen.parent


def wait_for_child(pid, timeout=1.0):
    deadline = time.time() + timeout
    while timeout < time.time():
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
        if broker.defer_sync(lambda: stream.pending_bytes()) == 0:
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
        self.assertEquals("ECORP_Administrator@box:123", self.func())


class WstatusToStrTest(testlib.TestCase):
    func = staticmethod(mitogen.parent.wstatus_to_str)

    def test_return_zero(self):
        pid = os.fork()
        if not pid:
            os._exit(0)
        (pid, status), _ = mitogen.core.io_op(os.waitpid, pid, 0)
        self.assertEquals(self.func(status),
                          'exited with return code 0')

    def test_return_one(self):
        pid = os.fork()
        if not pid:
            os._exit(1)
        (pid, status), _ = mitogen.core.io_op(os.waitpid, pid, 0)
        self.assertEquals(
            self.func(status),
            'exited with return code 1'
        )

    def test_sigkill(self):
        pid = os.fork()
        if not pid:
            time.sleep(600)
        os.kill(pid, signal.SIGKILL)
        (pid, status), _ = mitogen.core.io_op(os.waitpid, pid, 0)
        self.assertEquals(
            self.func(status),
            'exited due to signal %s (SIGKILL)' % (int(signal.SIGKILL),)
        )

    # can't test SIGSTOP without POSIX sessions rabbithole


class ReapChildTest(testlib.RouterMixin, testlib.TestCase):
    def test_connect_timeout(self):
        # Ensure the child process is reaped if the connection times out.
        stream = mitogen.parent.Stream(
            router=self.router,
            remote_id=1234,
            old_router=self.router,
            max_message_size=self.router.max_message_size,
            python_path=testlib.data_path('python_never_responds.py'),
            connect_timeout=0.5,
        )
        self.assertRaises(mitogen.core.TimeoutError,
            lambda: stream.connect()
        )
        wait_for_child(stream.pid)
        e = self.assertRaises(OSError,
            lambda: os.kill(stream.pid, 0)
        )
        self.assertEquals(e.args[0], errno.ESRCH)


class StreamErrorTest(testlib.RouterMixin, testlib.TestCase):
    def test_direct_eof(self):
        e = self.assertRaises(mitogen.core.StreamError,
            lambda: self.router.local(
                python_path='true',
                connect_timeout=3,
            )
        )
        prefix = "EOF on stream; last 300 bytes received: "
        self.assertTrue(e.args[0].startswith(prefix))

    def test_via_eof(self):
        # Verify FD leakage does not keep failed process open.
        local = self.router.local()
        e = self.assertRaises(mitogen.core.StreamError,
            lambda: self.router.local(
                via=local,
                python_path='true',
                connect_timeout=3,
            )
        )
        s = "EOF on stream; last 300 bytes received: "
        self.assertTrue(s in e.args[0])

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
        self.assertTrue(s in e.args[0])


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
        master_fd, slave_fd = self.func()
        self.assertTrue(isinstance(master_fd, int))
        self.assertTrue(isinstance(slave_fd, int))
        os.close(master_fd)
        os.close(slave_fd)

    @mock.patch('os.openpty')
    def test_max_reached(self, openpty):
        openpty.side_effect = OSError(errno.ENXIO)
        e = self.assertRaises(mitogen.core.StreamError,
                              lambda: self.func())
        msg = mitogen.parent.OPENPTY_MSG % (openpty.side_effect,)
        self.assertEquals(e.args[0], msg)

    @unittest2.skipIf(condition=(os.uname()[0] != 'Linux'),
                      reason='Fallback only supported on Linux')
    @mock.patch('os.openpty')
    def test_broken_linux_fallback(self, openpty):
        openpty.side_effect = OSError(errno.EPERM)
        master_fd, slave_fd = self.func()
        try:
            st = os.fstat(master_fd)
            self.assertEquals(5, os.major(st.st_rdev))
            flags = fcntl.fcntl(master_fd, fcntl.F_GETFL)
            self.assertTrue(flags & os.O_RDWR)

            st = os.fstat(slave_fd)
            self.assertEquals(136, os.major(st.st_rdev))
            flags = fcntl.fcntl(slave_fd, fcntl.F_GETFL)
            self.assertTrue(flags & os.O_RDWR)
        finally:
            os.close(master_fd)
            os.close(slave_fd)


class TtyCreateChildTest(testlib.TestCase):
    func = staticmethod(mitogen.parent.tty_create_child)

    def test_dev_tty_open_succeeds(self):
        # In the early days of UNIX, a process that lacked a controlling TTY
        # would acquire one simply by opening an existing TTY. Linux and OS X
        # continue to follow this behaviour, however at least FreeBSD moved to
        # requiring an explicit ioctl(). Linux supports it, but we don't yet
        # use it there and anyway the behaviour will never change, so no point
        # in fixing things that aren't broken. Below we test that
        # getpass-loving apps like sudo and ssh get our slave PTY when they
        # attempt to open /dev/tty, which is what they both do on attempting to
        # read a password.
        tf = tempfile.NamedTemporaryFile()
        try:
            pid, fd, _ = self.func([
                'bash', '-c', 'exec 2>%s; echo hi > /dev/tty' % (tf.name,)
            ])
            deadline = time.time() + 5.0
            for line in mitogen.parent.iter_read([fd], deadline):
                self.assertEquals(mitogen.core.b('hi\n'), line)
                break
            waited_pid, status = os.waitpid(pid, 0)
            self.assertEquals(pid, waited_pid)
            self.assertEquals(0, status)
            self.assertEquals(mitogen.core.b(''), tf.read())
            os.close(fd)
        finally:
            tf.close()


class IterReadTest(testlib.TestCase):
    func = staticmethod(mitogen.parent.iter_read)

    def make_proc(self):
        # I produce text every 100ms.
        args = [testlib.data_path('iter_read_generator.py')]
        proc = subprocess.Popen(args, stdout=subprocess.PIPE)
        mitogen.core.set_nonblock(proc.stdout.fileno())
        return proc

    def test_no_deadline(self):
        proc = self.make_proc()
        try:
            reader = self.func([proc.stdout.fileno()])
            for i, chunk in enumerate(reader):
                self.assertEqual(1+i, int(chunk))
                if i > 2:
                    break
        finally:
            Popen__terminate(proc)
            proc.stdout.close()

    def test_deadline_exceeded_before_call(self):
        proc = self.make_proc()
        reader = self.func([proc.stdout.fileno()], 0)
        try:
            got = []
            try:
                for chunk in reader:
                    got.append(chunk)
                assert 0, 'TimeoutError not raised'
            except mitogen.core.TimeoutError:
                self.assertEqual(len(got), 0)
        finally:
            Popen__terminate(proc)
            proc.stdout.close()

    def test_deadline_exceeded_during_call(self):
        proc = self.make_proc()
        deadline = time.time() + 0.4

        reader = self.func([proc.stdout.fileno()], deadline)
        try:
            got = []
            try:
                for chunk in reader:
                    if time.time() > (deadline + 1.0):
                        assert 0, 'TimeoutError not raised'
                    got.append(chunk)
            except mitogen.core.TimeoutError:
                # Give a little wiggle room in case of imperfect scheduling.
                # Ideal number should be 9.
                self.assertLess(deadline, time.time())
                self.assertLess(1, len(got))
                self.assertLess(len(got), 20)
        finally:
            Popen__terminate(proc)
            proc.stdout.close()


class WriteAllTest(testlib.TestCase):
    func = staticmethod(mitogen.parent.write_all)

    def make_proc(self):
        args = [testlib.data_path('write_all_consumer.py')]
        proc = subprocess.Popen(args, stdin=subprocess.PIPE)
        mitogen.core.set_nonblock(proc.stdin.fileno())
        return proc

    ten_ms_chunk = (mitogen.core.b('x') * 65535)

    def test_no_deadline(self):
        proc = self.make_proc()
        try:
            self.func(proc.stdin.fileno(), self.ten_ms_chunk)
        finally:
            Popen__terminate(proc)
            proc.stdin.close()

    def test_deadline_exceeded_before_call(self):
        proc = self.make_proc()
        try:
            self.assertRaises(mitogen.core.TimeoutError, (
                lambda: self.func(proc.stdin.fileno(), self.ten_ms_chunk, 0)
            ))
        finally:
            Popen__terminate(proc)
            proc.stdin.close()

    def test_deadline_exceeded_during_call(self):
        proc = self.make_proc()
        try:
            deadline = time.time() + 0.1   # 100ms deadline
            self.assertRaises(mitogen.core.TimeoutError, (
                lambda: self.func(proc.stdin.fileno(),
                                  self.ten_ms_chunk * 100,  # 1s of data
                                  deadline)
            ))
        finally:
            Popen__terminate(proc)
            proc.stdin.close()


class DisconnectTest(testlib.RouterMixin, testlib.TestCase):
    def test_child_disconnected(self):
        # Easy mode: process notices its own directly connected child is
        # disconnected.
        c1 = self.router.local()
        recv = c1.call_async(time.sleep, 9999)
        c1.shutdown(wait=True)
        e = self.assertRaises(mitogen.core.ChannelError,
            lambda: recv.get())
        self.assertEquals(e.args[0], self.router.respondent_disconnect_msg)

    def test_indirect_child_disconnected(self):
        # Achievement unlocked: process notices an indirectly connected child
        # is disconnected.
        c1 = self.router.local()
        c2 = self.router.local(via=c1)
        recv = c2.call_async(time.sleep, 9999)
        c2.shutdown(wait=True)
        e = self.assertRaises(mitogen.core.ChannelError,
            lambda: recv.get())
        self.assertEquals(e.args[0], self.router.respondent_disconnect_msg)

    def test_indirect_child_intermediary_disconnected(self):
        # Battlefield promotion: process notices indirect child disconnected
        # due to an intermediary child disconnecting.
        c1 = self.router.local()
        c2 = self.router.local(via=c1)
        recv = c2.call_async(time.sleep, 9999)
        c1.shutdown(wait=True)
        e = self.assertRaises(mitogen.core.ChannelError,
            lambda: recv.get())
        self.assertEquals(e.args[0], self.router.respondent_disconnect_msg)

    def test_near_sibling_disconnected(self):
        # Hard mode: child notices sibling connected to same parent has
        # disconnected.
        c1 = self.router.local()
        c2 = self.router.local()

        # Let c1 call functions in c2.
        self.router.stream_by_id(c1.context_id).auth_id = mitogen.context_id
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
        c1 = self.router.local()
        c11 = self.router.local(via=c1)

        c2 = self.router.local()
        c22 = self.router.local(via=c2)

        # Let c1 call functions in c2.
        self.router.stream_by_id(c1.context_id).auth_id = mitogen.context_id
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


if __name__ == '__main__':
    unittest2.main()
