
import unittest2 as unittest

import testlib
import id_allocation


class SlaveTest(testlib.RouterMixin, testlib.TestCase):
    def test_slave_allocates_id(self):
        context = self.router.local()
        id_ = context.call(id_allocation.allocate_an_id)
        assert id_ == (self.router.id_allocator.next_id - 1)


if __name__ == '__main__':
    unittest.main()
