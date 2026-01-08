import sys
import unittest

import testlib
import resourced_pkg
import resourced_pkg.sub_pkg

@unittest.skipIf(sys.version_info < (3, 7), 'importlib.resources, Python >= 3.7')
class ResourceReaderBaselineTest(testlib.TestCase):
    'Assert out-the-box stdlib behaviours to cross validate remote tests.'
    def test_is_resource(self):
        import importlib.resources

        self.assertFalse(importlib.resources.is_resource(resourced_pkg, 'does_not_exist'))
        self.assertFalse(importlib.resources.is_resource(resourced_pkg, 'sub_dir'))
        self.assertFalse(importlib.resources.is_resource(resourced_pkg.sub_pkg, 'does_not_exist'))

        self.assertTrue(importlib.resources.is_resource(resourced_pkg, 'binary'))
        self.assertTrue(importlib.resources.is_resource(resourced_pkg, 'empty'))
        self.assertTrue(importlib.resources.is_resource(resourced_pkg, 'text.txt'))
        self.assertTrue(importlib.resources.is_resource(resourced_pkg, 'sub_dir/empty'))
        self.assertTrue(importlib.resources.is_resource(resourced_pkg.sub_pkg, 'text.txt'))


@unittest.skipIf(sys.version_info < (3, 7), 'importlib.resources, Python >= 3.7')
class ResourceReaderTest(testlib.RouterMixin, testlib.TestCase):
    def call_is_resource(self, conn):
        import importlib.resources

        self.assertFalse(conn.call(importlib.resources.is_resource, 'resourced_pkg', 'does_not_exist'))
        self.assertFalse(conn.call(importlib.resources.is_resource, 'resourced_pkg', 'sub_dir'))
        self.assertFalse(conn.call(importlib.resources.is_resource, 'resourced_pkg.sub_pkg', 'does_not_exist'))

        self.assertTrue(conn.call(importlib.resources.is_resource, 'resourced_pkg', 'binary'))
        self.assertTrue(conn.call(importlib.resources.is_resource, 'resourced_pkg', 'empty'))
        self.assertTrue(conn.call(importlib.resources.is_resource, 'resourced_pkg', 'text.txt'))
        self.assertTrue(conn.call(importlib.resources.is_resource, 'resourced_pkg', 'sub_dir/empty'))
        self.assertTrue(conn.call(importlib.resources.is_resource, 'resourced_pkg.sub_pkg', 'text.txt'))

    def test_is_resource(self):
        # Uses the same version of Python so we can be sure importlib.resources is present
        # TODO Cross Python version tests
        connection = self.router.local(python_path=sys.executable)
        self.call_is_resource(conn=connection)

    def test_is_resource_2_hops(self):
        # Uses the same version of Python so we can be sure importlib.resources is present
        # TODO Cross Python version tests
        hop_one = self.router.local(python_path=sys.executable)
        hop_two = self.router.local(python_path=sys.executable, via=hop_one)
        self.call_is_resource(conn=hop_two)
