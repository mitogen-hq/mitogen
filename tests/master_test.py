import inspect

import unittest2

import testlib
import mitogen.master


class ScanCodeImportsTest(unittest2.TestCase):
    func = staticmethod(mitogen.master.scan_code_imports)

    def test_simple(self):
        source_path = inspect.getsourcefile(ScanCodeImportsTest)
        co = compile(open(source_path).read(), source_path, 'exec')
        self.assertEquals(list(self.func(co)), [
            (-1, 'inspect', ()),
            (-1, 'unittest2', ()),
            (-1, 'testlib', ()),
            (-1, 'mitogen.master', ()),
        ])


if __name__ == '__main__':
    unittest2.main()
