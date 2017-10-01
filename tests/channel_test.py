import unittest

import mitogen.core
import testlib


class ConstructorTest(testlib.RouterMixin, testlib.TestCase):
    def test_constructor(self):
        # issue 32
        l1 = self.router.local()
        chan = mitogen.core.Channel(self.router, l1, 123)
        assert chan.router == self.router
        assert chan.context == l1
        assert chan.dst_handle == 123
        assert chan.handle is not None
        assert chan.handle > 0


if __name__ == '__main__':
    unittest.main()
