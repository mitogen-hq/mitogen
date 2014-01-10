#!/usr/bin/env python2.5

"""
def DoStuff():
    import time
    file('/tmp/foobar', 'w').write(time.ctime())


localhost = pyrpc.SSHConnection('localhost')
localhost.Connect()
try:
    ret = localhost.Evaluate(DoStuff)
except OSError, e:
    


Tests
    - Test Channel objects to destruction.
    - External contexts sometimes don't appear to die during a crash. This needs
        tested to destruction.
    - Test reconnecting to previously idle-killed contexts.
    - Test remote context longevity to destruction. They should never stay
        around after parent dies or disconnects.

"""

import sys
import unittest
import econtext



#
# Helper functions.
#

class GetModuleImportsTestCase(unittest.TestCase):
    # This must be kept in sync with our actual imports.
    IMPORTS = [
        ('econtext', 'econtext'),
        ('sys', 'PythonSystemModule'),
        ('sys', 'sys'),
        ('unittest', 'unittest')
    ]

    def setUp(self):
        global PythonSystemModule
        import sys as PythonSystemModule

    def tearDown(Self):
        global PythonSystemModule
        del PythonSystemModule

    def testImports(self):
        self.assertEqual(set(self.IMPORTS),
                                         set(econtext.GetModuleImports(sys.modules[__name__])))


class BuildPartialModuleTestCase(unittest.TestCase):
    def testNullModule(self):
        """Pass empty sequences; result should contain nothing but a hash bang line
        and whitespace."""

        lines = econtext.BuildPartialModule([], []).strip().split('\n')

        self.assert_(lines[0].startswith('#!'))
        self.assert_('import' not in lines[1:])

    def testPassingMethodTypeFails(self):
        """Pass an instance method and ensure we refuse it."""

        self.assertRaises(TypeError, econtext.BuildPartialModule,
                                            [self.testPassingMethodTypeFails], [])

    @staticmethod
    def exampleStaticMethod():
        pass

    def testStaticMethodGetsUnwrapped(self):
        "Ensure that @staticmethod decorators are stripped."

        dct = {}
        exec econtext.BuildPartialModule([self.exampleStaticMethod], []) in dct
        self.assertFalse(isinstance(dct['exampleStaticMethod'], staticmethod))



#
# Streams
#

class StreamTestBase:
    """This defines rules that should remain true for all Stream subclasses. We
    test in this manner to guard against a subclass breaking Stream's
    polymorphism (e.g. overriding a method with the wrong prototype).

        def testCommandLine(self):
            print self.driver.command_line
    """


class SSHStreamTestCase(unittest.TestCase, StreamTestBase):
    DRIVER_CLASS = econtext.SSHStream

    def setUp(self):
        # Stubs.

        # Instance initialization.
        self.stream = econtext.SSHStream('localhost', 'test-agent')

    def tearDown(self):
        pass

    def testConstructor(self):
        pass


class TCPStreamTestCase(unittest.TestCase, StreamTestBase):
    pass


#
# Run the tests.
#

if __name__ == '__main__':
    unittest.main()
