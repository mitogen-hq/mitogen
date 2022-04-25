import mitogen.core
import mitogen.service
import testlib


class MyService(mitogen.service.Service):
    def __init__(self, router):
        super(MyService, self).__init__(router)
        self._counter = 0

    @mitogen.service.expose(policy=mitogen.service.AllowParents())
    def get_id(self):
        self._counter += 1
        return self._counter, id(self)

    @mitogen.service.expose(policy=mitogen.service.AllowParents())
    @mitogen.service.arg_spec({
        'foo': int
    })
    def test_arg_spec(self, foo):
        return foo

    @mitogen.service.expose(policy=mitogen.service.AllowParents())
    def privileged_op(self):
        return 'privileged!'

    @mitogen.service.expose(policy=mitogen.service.AllowAny())
    def unprivileged_op(self):
        return 'unprivileged!'


class MyService2(MyService):
    """
    A uniquely named service that lets us test framework activation and class
    activation separately.
    """


def call_service_in(context, service_name, method_name):
    return context.call_service(service_name, method_name)


class CallTest(testlib.RouterMixin, testlib.TestCase):
    def test_local(self):
        pool = mitogen.service.get_or_create_pool(router=self.router)
        self.assertEqual(
            'privileged!',
            mitogen.service.call(MyService, 'privileged_op')
        )
        pool.stop()

    def test_remote_bad_arg(self):
        c1 = self.router.local()
        self.assertRaises(
            mitogen.core.CallError,
            lambda: mitogen.service.call(
                MyService.name(),
                'test_arg_spec',
                foo='x',
                call_context=c1
            )
        )

    def test_local_unicode(self):
        pool = mitogen.service.get_or_create_pool(router=self.router)
        self.assertEqual(
            'privileged!',
            mitogen.service.call(MyService.name(), 'privileged_op')
        )
        pool.stop()

    def test_remote(self):
        c1 = self.router.local()
        self.assertEqual(
            'privileged!',
            mitogen.service.call(MyService, 'privileged_op',
                                 call_context=c1)
        )


class ActivationTest(testlib.RouterMixin, testlib.TestCase):
    def test_parent_can_activate(self):
        l1 = self.router.local()
        counter, id_ = l1.call_service(MyService, 'get_id')
        self.assertEqual(1, counter)
        self.assertTrue(isinstance(id_, int))

    def test_sibling_cannot_activate_framework(self):
        l1 = self.router.local(name='l1')
        l2 = self.router.local(name='l2')
        exc = self.assertRaises(mitogen.core.CallError,
            lambda: l2.call(call_service_in, l1, MyService2.name(), 'get_id'))
        self.assertTrue(mitogen.core.Router.refused_msg in exc.args[0])

    def test_sibling_cannot_activate_service(self):
        l1 = self.router.local()
        l2 = self.router.local()
        l1.call_service(MyService, 'get_id')  # force framework activation
        capture = testlib.LogCapturer()
        capture.start()
        try:
            exc = self.assertRaises(mitogen.core.CallError,
                lambda: l2.call(call_service_in, l1, MyService2.name(), 'get_id'))
        finally:
            capture.stop()
        msg = mitogen.service.Activator.not_active_msg % (MyService2.name(),)
        self.assertTrue(msg in exc.args[0])

    def test_activates_only_once(self):
        l1 = self.router.local()
        counter, id_ = l1.call_service(MyService, 'get_id')
        counter2, id_2 = l1.call_service(MyService, 'get_id')
        self.assertEqual(1, counter)
        self.assertEqual(2, counter2)
        self.assertEqual(id_, id_2)


class PermissionTest(testlib.RouterMixin, testlib.TestCase):
    def test_sibling_unprivileged_ok(self):
        l1 = self.router.local()
        l1.call_service(MyService, 'get_id')
        l2 = self.router.local()
        self.assertEqual('unprivileged!',
            l2.call(call_service_in, l1, MyService.name(), 'unprivileged_op'))

    def test_sibling_privileged_bad(self):
        l1 = self.router.local()
        l1.call_service(MyService, 'get_id')
        l2 = self.router.local()
        capture = testlib.LogCapturer()
        capture.start()
        try:
            exc = self.assertRaises(mitogen.core.CallError, lambda:
                l2.call(call_service_in, l1, MyService.name(), 'privileged_op'))
        finally:
            capture.stop()
        msg = mitogen.service.Invoker.unauthorized_msg % (
            u'privileged_op',
            MyService.name(),
        )
        self.assertTrue(msg in exc.args[0])


class CloseTest(testlib.RouterMixin, testlib.TestCase):
    klass = mitogen.service.Pool

    def test_receiver_closed(self):
        pool = self.klass(router=self.router, services=[])
        pool.stop()
        self.assertEqual(None, pool._receiver.handle)

        e = self.assertRaises(mitogen.core.ChannelError,
            lambda: self.router.myself().call_service(MyService, 'foobar'))
        self.assertEqual(e.args[0], self.router.invalid_handle_msg)
