
import unittest
import mitogen.master


class CompilerModuleTest(unittest.TestCase):
    klass = mitogen.master.ModuleScanner

    @classmethod
    def setUpClass(cls):
        super(CompilerModuleTest, cls).setUpClass()
        #import compiler
        #mitogen.master.ast = None
        #mitogen.master.compiler = compiler

    def test_simple(self):
        for x in range(100):
            finder = self.klass()
            from pprint import pprint
            import time
            t0 = time.time()
            import mitogen.fakessh
            pprint(finder.find_related('mitogen.fakessh'))
            print 1000 * (time.time() - t0)


if __name__ == '__main__':
    unittest.main()
