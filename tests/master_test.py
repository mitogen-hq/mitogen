import inspect

import mitogen.core
import mitogen.imports

import testlib


class ScanCodeImportsTest(testlib.TestCase):
    func = staticmethod(mitogen.imports.scan_code_imports)

    if mitogen.core.PY3:
        level = 0
    else:
        level = -1

    SIMPLE_EXPECT = [
        (level, 'inspect', ()),
        (level, 'mitogen.core', ()),
        (level, 'mitogen.imports', ()),
        (level, 'testlib', ()),
    ]

    def test_simple(self):
        source_path = inspect.getsourcefile(ScanCodeImportsTest)
        with open(source_path) as f:
            co = compile(f.read(), source_path, 'exec')
        self.assertEqual(list(self.func(co)), self.SIMPLE_EXPECT)
