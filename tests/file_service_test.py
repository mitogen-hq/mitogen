
import unittest2

import mitogen.service

import testlib


class FetchTest(testlib.RouterMixin, testlib.TestCase):
    klass = mitogen.service.FileService

    def test_unauthorized(self):
        service = self.klass(self.router)
        e = self.assertRaises(mitogen.service.Error,
            lambda: service.fetch(
                path='/etc/shadow',
                sender=None,
                msg=mitogen.core.Message(),
            )
        )

        self.assertEquals(e.args[0], service.unregistered_msg)

    def test_path_authorized(self):
        recv = mitogen.core.Receiver(self.router)
        service = self.klass(self.router)
        service.register('/etc/passwd')
        self.assertEquals(None, service.fetch(
            path='/etc/passwd',
            sender=recv.to_sender(),
            msg=mitogen.core.Message(),
        ))

    def test_root_authorized(self):
        recv = mitogen.core.Receiver(self.router)
        service = self.klass(self.router)
        service.register_prefix('/')
        self.assertEquals(None, service.fetch(
            path='/etc/passwd',
            sender=recv.to_sender(),
            msg=mitogen.core.Message(),
        ))

    def test_prefix_authorized(self):
        recv = mitogen.core.Receiver(self.router)
        service = self.klass(self.router)
        service.register_prefix('/etc')
        self.assertEquals(None, service.fetch(
            path='/etc/passwd',
            sender=recv.to_sender(),
            msg=mitogen.core.Message(),
        ))

    def test_prefix_authorized_abspath_bad(self):
        recv = mitogen.core.Receiver(self.router)
        service = self.klass(self.router)
        service.register_prefix('/etc')
        self.assertEquals(None, service.fetch(
            path='/etc/foo/bar/../../../passwd',
            sender=recv.to_sender(),
            msg=mitogen.core.Message(),
        ))

    def test_prefix_authorized_abspath_bad(self):
        recv = mitogen.core.Receiver(self.router)
        service = self.klass(self.router)
        service.register_prefix('/etc')
        e = self.assertRaises(mitogen.service.Error,
            lambda: service.fetch(
                path='/etc/../shadow',
                sender=recv.to_sender(),
                msg=mitogen.core.Message(),
            )
        )

        self.assertEquals(e.args[0], service.unregistered_msg)



if __name__ == '__main__':
    unittest2.main()
