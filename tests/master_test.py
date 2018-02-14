
import unittest2

import testlib
import mitogen.master


class ScanCodeImportsTest(unittest2.TestCase):
    func = staticmethod(mitogen.master.scan_code_imports)

    def test_simple(self):
        co = compile(open(__file__).read(), __file__, 'exec')
        self.assertEquals(list(self.func(co)), [
            (-1, 'unittest2', ()),
            (-1, 'testlib', ()),
            (-1, 'mitogen.master', ()),
        ])


if __name__ == '__main__':
    unittest2.main()
