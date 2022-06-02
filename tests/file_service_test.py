import sys

import mitogen.service

import testlib


class FetchTest(testlib.RouterMixin, testlib.TestCase):
    klass = mitogen.service.FileService

    def replyable_msg(self, **kwargs):
        recv = mitogen.core.Receiver(self.router, persist=False)
        msg = mitogen.core.Message(
            src_id=mitogen.context_id,
            reply_to=recv.handle,
            **kwargs
        )
        msg.router = self.router
        return recv, msg

    def test_unauthorized(self):
        l1 = self.router.local()

        service = self.klass(self.router)
        pool = mitogen.service.Pool(
            router=self.router,
            services=[service],
            size=1,
        )
        try:
            e = self.assertRaises(mitogen.core.CallError,
                lambda: l1.call(
                    mitogen.service.FileService.get,
                    context=self.router.myself(),
                    path='/etc/shadow',
                    out_fp=None,
                )
            )
        finally:
            pool.stop()

        expect = service.unregistered_msg % ('/etc/shadow',)
        self.assertTrue(expect in e.args[0])

    if sys.platform == 'darwin':
        ROOT_GROUP = 'wheel'
    else:
        ROOT_GROUP = 'root'

    def _validate_response(self, resp):
        self.assertTrue(isinstance(resp, dict))
        self.assertEqual('root', resp['owner'])
        self.assertEqual(self.ROOT_GROUP, resp['group'])
        self.assertTrue(isinstance(resp['mode'], int))
        self.assertTrue(isinstance(resp['mtime'], float))
        self.assertTrue(isinstance(resp['atime'], float))
        self.assertTrue(isinstance(resp['size'], int))

    def test_path_authorized(self):
        recv = mitogen.core.Receiver(self.router)
        service = self.klass(self.router)
        service.register('/etc/passwd')
        recv, msg = self.replyable_msg()
        service.fetch(
            path='/etc/passwd',
            sender=recv.to_sender(),
            msg=msg,
        )
        self._validate_response(recv.get().unpickle())

    def test_root_authorized(self):
        recv = mitogen.core.Receiver(self.router)
        service = self.klass(self.router)
        service.register_prefix('/')
        recv, msg = self.replyable_msg()
        service.fetch(
            path='/etc/passwd',
            sender=recv.to_sender(),
            msg=msg,
        )
        self._validate_response(recv.get().unpickle())

    def test_prefix_authorized(self):
        recv = mitogen.core.Receiver(self.router)
        service = self.klass(self.router)
        service.register_prefix('/etc')
        recv, msg = self.replyable_msg()
        service.fetch(
            path='/etc/passwd',
            sender=recv.to_sender(),
            msg=msg,
        )
        self._validate_response(recv.get().unpickle())

    def test_prefix_authorized_abspath_bad(self):
        l1 = self.router.local()

        service = self.klass(self.router)
        service.register_prefix('/etc')

        pool = mitogen.service.Pool(
            router=self.router,
            services=[service],
            size=1,
        )
        path = '/etc/foo/bar/../../../passwd'
        try:
            e = self.assertRaises(mitogen.core.CallError,
                lambda: l1.call(
                    mitogen.service.FileService.get,
                    context=self.router.myself(),
                    path=path,
                    out_fp=None,
                )
            )
        finally:
            pool.stop()

        expect = service.unregistered_msg % (path,)
        self.assertTrue(expect in e.args[0])

    def test_prefix_authorized_abspath_good(self):
        l1 = self.router.local()

        service = self.klass(self.router)
        service.register_prefix('/etc')
        path = '/etc/../shadow'

        pool = mitogen.service.Pool(
            router=self.router,
            services=[service],
            size=1,
        )
        try:
            e = self.assertRaises(mitogen.core.CallError,
                lambda: l1.call(
                    mitogen.service.FileService.get,
                    context=self.router.myself(),
                    path=path,
                    out_fp=None
                )
            )
        finally:
            pool.stop()

        expect = service.unregistered_msg % (path,)
        self.assertTrue(expect in e.args[0])
