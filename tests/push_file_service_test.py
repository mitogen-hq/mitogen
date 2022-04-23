import tempfile

import mitogen.core
import mitogen.service
import testlib
from mitogen.core import b


def prepare():
    # ensure module loading delay is complete before loading PushFileService.
    pass


@mitogen.core.takes_router
def wait_for_file(path, router):
    pool = mitogen.service.get_or_create_pool(router=router)
    service = pool.get_service(u'mitogen.service.PushFileService')
    return service.get(path)


class PropagateToTest(testlib.RouterMixin, testlib.TestCase):
    klass = mitogen.service.PushFileService

    def test_two_grandchild_one_intermediary(self):
        tf = tempfile.NamedTemporaryFile()
        path = mitogen.core.to_text(tf.name)

        try:
            tf.write(b('test'))
            tf.flush()

            interm = self.router.local(name='interm')
            c1 = self.router.local(via=interm, name='c1')
            c2 = self.router.local(via=interm)

            c1.call(prepare)
            c2.call(prepare)

            service = self.klass(router=self.router)
            service.propagate_to(context=c1, path=path)
            service.propagate_to(context=c2, path=path)

            s = c1.call(wait_for_file, path=path)
            self.assertEqual(b('test'), s)

            s = c2.call(wait_for_file, path=path)
            self.assertEqual(b('test'), s)
        finally:
            tf.close()
