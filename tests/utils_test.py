#!/usr/bin/env python

import os
import tempfile

import unittest2
import mock

import mitogen.core
import mitogen.parent
import mitogen.master
import mitogen.utils
from mitogen.core import b

import testlib


def func0(router):
    return router


@mitogen.utils.with_router
def func(router):
    return router


class ResetAffinityTest(testlib.TestCase):
    func = staticmethod(mitogen.utils.reset_affinity)

    def _get_cpus(self, path='/proc/self/status'):
        fp = open(path)
        try:
            for line in fp:
                if line.startswith('Cpus_allowed'):
                    return int(line.split()[1], 16)
        finally:
            fp.close()

    @mock.patch('random.randint')
    def test_set_reset(self, randint):
        randint.return_value = 3
        before = self._get_cpus()
        self.func()
        self.assertEquals(self._get_cpus(), 1 << 3)
        self.func(clear=True)
        self.assertEquals(self._get_cpus(), before)

    @mock.patch('random.randint')
    def test_clear_on_popen(self, randint):
        randint.return_value = 3
        tf = tempfile.NamedTemporaryFile()
        try:
            before = self._get_cpus()
            self.func()
            my_cpu = self._get_cpus()

            pid = mitogen.parent.detach_popen(
                args=['cp', '/proc/self/status', tf.name]
            )
            os.waitpid(pid, 0)

            his_cpu = self._get_cpus(tf.name)
            self.assertNotEquals(my_cpu, his_cpu)
            self.func(clear=True)
        finally:
            tf.close()

ResetAffinityTest = unittest2.skipIf(
    reason='Linux only',
    condition=os.uname()[0] != 'Linux'
)(ResetAffinityTest)


class RunWithRouterTest(testlib.TestCase):
    # test_shutdown_on_exception
    # test_shutdown_on_success

    def test_run_with_broker(self):
        router = mitogen.utils.run_with_router(func0)
        self.assertIsInstance(router, mitogen.master.Router)
        self.assertFalse(router.broker._thread.isAlive())


class WithRouterTest(testlib.TestCase):
    def test_with_broker(self):
        router = func()
        self.assertIsInstance(router, mitogen.master.Router)
        self.assertFalse(router.broker._thread.isAlive())


class Dict(dict): pass
class List(list): pass
class Tuple(tuple): pass
class Unicode(mitogen.core.UnicodeType): pass
class Bytes(mitogen.core.BytesType): pass


class CastTest(testlib.TestCase):
    def test_dict(self):
        self.assertEqual(type(mitogen.utils.cast({})), dict)
        self.assertEqual(type(mitogen.utils.cast(Dict())), dict)

    def test_nested_dict(self):
        specimen = mitogen.utils.cast(Dict({'k': Dict({'k2': 'v2'})}))
        self.assertEqual(type(specimen), dict)
        self.assertEqual(type(specimen['k']), dict)

    def test_list(self):
        self.assertEqual(type(mitogen.utils.cast([])), list)
        self.assertEqual(type(mitogen.utils.cast(List())), list)

    def test_nested_list(self):
        specimen = mitogen.utils.cast(List((0, 1, List((None,)))))
        self.assertEqual(type(specimen), list)
        self.assertEqual(type(specimen[2]), list)

    def test_tuple(self):
        self.assertEqual(type(mitogen.utils.cast(())), list)
        self.assertEqual(type(mitogen.utils.cast(Tuple())), list)

    def test_nested_tuple(self):
        specimen = mitogen.utils.cast(Tuple((0, 1, Tuple((None,)))))
        self.assertEqual(type(specimen), list)
        self.assertEqual(type(specimen[2]), list)

    def assertUnchanged(self, v):
        self.assertIs(mitogen.utils.cast(v), v)

    def test_passthrough(self):
        self.assertUnchanged(0)
        self.assertUnchanged(0.0)
        self.assertUnchanged(float('inf'))
        self.assertUnchanged(True)
        self.assertUnchanged(False)
        self.assertUnchanged(None)

    def test_unicode(self):
        self.assertEqual(type(mitogen.utils.cast(u'')), mitogen.core.UnicodeType)
        self.assertEqual(type(mitogen.utils.cast(Unicode())), mitogen.core.UnicodeType)

    def test_bytes(self):
        self.assertEqual(type(mitogen.utils.cast(b(''))), mitogen.core.BytesType)
        self.assertEqual(type(mitogen.utils.cast(Bytes())), mitogen.core.BytesType)

    def test_unknown(self):
        self.assertRaises(TypeError, mitogen.utils.cast, set())
        self.assertRaises(TypeError, mitogen.utils.cast, 4j)


if __name__ == '__main__':
    unittest2.main()
