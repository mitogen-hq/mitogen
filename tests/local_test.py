import os
import sys

import testlib


def get_sys_executable():
    return sys.executable


def get_os_environ():
    return dict(os.environ)


class ConstructionTest(testlib.RouterMixin, testlib.TestCase):
    stub_python_path = testlib.data_path('stubs/stub-python.py')

    def test_stream_name(self):
        context = self.router.local()
        pid = context.call(os.getpid)
        self.assertEqual('local.%d' % (pid,), context.name)

    def test_python_path_inherited(self):
        context = self.router.local()
        self.assertEqual(sys.executable, context.call(get_sys_executable))

    def test_python_path_string(self):
        context = self.router.local(
            python_path=self.stub_python_path,
        )
        env = context.call(get_os_environ)
        self.assertEqual('1', env['THIS_IS_STUB_PYTHON'])

    def test_python_path_list(self):
        context = self.router.local(
            python_path=[
                self.stub_python_path,
                "magic_first_arg",
                sys.executable
            ]
        )
        self.assertEqual(sys.executable, context.call(get_sys_executable))
        env = context.call(get_os_environ)
        self.assertEqual('magic_first_arg', env['STUB_PYTHON_FIRST_ARG'])
        self.assertEqual('1', env['THIS_IS_STUB_PYTHON'])
