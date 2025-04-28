import unittest

import mitogen.core

import testlib
import simple_pkg.ping


# TODO: this is a joke. 2/3 interop is one of the hardest bits to get right.
# There should be 100 tests in this file.

@unittest.skipIf(
    not testlib.have_python2() or not testlib.have_python3(),
    "Python 2/3 compatibility tests require both versions on the controller",
)
class TwoThreeCompatTest(testlib.RouterMixin, testlib.TestCase):
    if mitogen.core.PY3:
        python_path = 'python2'
    else:
        python_path = 'python3'

    def test_succeeds(self):
        spare = self.router.local()
        target = self.router.local(python_path=self.python_path)

        spare2, = target.call(simple_pkg.ping.ping, spare)
        self.assertEqual(spare.context_id, spare2.context_id)
        self.assertEqual(spare.name, spare2.name)
