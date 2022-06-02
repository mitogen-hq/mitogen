import os
import socket
import subprocess
import sys
import time

import mitogen
import mitogen.master
import mitogen.service
import mitogen.unix

import testlib


class MyService(mitogen.service.Service):
    def __init__(self, latch, **kwargs):
        super(MyService, self).__init__(**kwargs)
        # used to wake up main thread once client has made its request
        self.latch = latch

    @classmethod
    def name(cls):
        # Because this is loaded from both __main__ and whatever unit2 does,
        # specify a fixed name.
        return 'unix_test.MyService'

    @mitogen.service.expose(policy=mitogen.service.AllowParents())
    def ping(self, msg):
        self.latch.put(None)
        return {
            'src_id': msg.src_id,
            'auth_id': msg.auth_id,
        }


class IsPathDeadTest(testlib.TestCase):
    func = staticmethod(mitogen.unix.is_path_dead)
    path = '/tmp/stale-socket'

    def test_does_not_exist(self):
        self.assertTrue(self.func('/tmp/does-not-exist'))

    def make_socket(self):
        if os.path.exists(self.path):
            os.unlink(self.path)
        s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        s.bind(self.path)
        return s

    def test_conn_refused(self):
        s = self.make_socket()
        s.close()
        self.assertTrue(self.func(self.path))

    def test_is_alive(self):
        s = self.make_socket()
        s.listen(5)
        self.assertFalse(self.func(self.path))
        s.close()
        os.unlink(self.path)


class ListenerTest(testlib.RouterMixin, testlib.TestCase):
    klass = mitogen.unix.Listener

    def test_constructor_basic(self):
        listener = self.klass.build_stream(router=self.router)
        capture = testlib.LogCapturer()
        capture.start()
        try:
            self.assertFalse(mitogen.unix.is_path_dead(listener.protocol.path))
            os.unlink(listener.protocol.path)
            # ensure we catch 0 byte read error log message
            self.broker.shutdown()
            self.broker.join()
            self.broker_shutdown = True
        finally:
            capture.stop()


class ClientTest(testlib.TestCase):
    klass = mitogen.unix.Listener

    def _try_connect(self, path):
        # give server a chance to setup listener
        timeout = mitogen.core.now() + 30.0
        while True:
            try:
                return mitogen.unix.connect(path)
            except mitogen.unix.ConnectError:
                if mitogen.core.now() > timeout:
                    raise
                time.sleep(0.1)

    def _test_simple_client(self, path):
        router, context = self._try_connect(path)
        try:
            self.assertEqual(0, context.context_id)
            self.assertEqual(1, mitogen.context_id)
            self.assertEqual(0, mitogen.parent_id)
            resp = context.call_service(service_name=MyService, method_name='ping')
            self.assertEqual(mitogen.context_id, resp['src_id'])
            self.assertEqual(0, resp['auth_id'])
        finally:
            router.broker.shutdown()
            router.broker.join()
            os.unlink(path)

    @classmethod
    def _test_simple_server(cls, path):
        router = mitogen.master.Router()
        latch = mitogen.core.Latch()
        try:
            try:
                listener = cls.klass.build_stream(path=path, router=router)
                pool = mitogen.service.Pool(router=router, services=[
                    MyService(latch=latch, router=router),
                ])
                latch.get()
                # give broker a chance to deliver service resopnse
                time.sleep(0.1)
            finally:
                pool.shutdown()
                pool.join()
                router.broker.shutdown()
                router.broker.join()
        finally:
            os._exit(0)

    def test_simple(self):
        path = mitogen.unix.make_socket_path()
        proc = subprocess.Popen(
            [sys.executable, __file__, 'ClientTest_server', path]
        )
        try:
            self._test_simple_client(path)
        finally:
            # TODO :)
            mitogen.context_id = 0
            mitogen.parent_id = None
            mitogen.parent_ids = []
        proc.wait()


if __name__ == '__main__':
    if len(sys.argv) == 3 and sys.argv[1] == 'ClientTest_server':
        ClientTest._test_simple_server(path=sys.argv[2])
