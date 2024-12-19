#
# Print data structure diff on assertion failure.
#
# assert_equal:  left=some.result right={1:2}
#

__metaclass__ = type

import inspect
import unittest

import ansible.template

from ansible.plugins.action import ActionBase


TEMPLATE_KWARGS = {}

try:
    # inspect.getfullargspec()  Added: 3.0
    _argspec = inspect.getfullargspec(ansible.template.Templar.template)
except AttributeError:
    # inspect.getargspec()      Added: 2.1  Deprecated: 3.0  Removed: 3.11
    _argspec = inspect.getargspec(ansible.template.Templar.template)
if 'bare_deprecated' in _argspec.args:
    TEMPLATE_KWARGS['bare_deprecated'] = False


class TestCase(unittest.TestCase):
    def runTest(self):
        pass


def text_diff(a, b):
    tc = TestCase()
    tc.maxDiff = None
    try:
        tc.assertEqual(a, b)
        return None
    except AssertionError as e:
        return str(e)


class ActionModule(ActionBase):
    ''' Fail with custom message '''

    TRANSFERS_FILES = False
    _VALID_ARGS = frozenset(('left', 'right'))

    def template(self, obj):
        return self._templar.template(
            obj,
            convert_bare=True,
            **TEMPLATE_KWARGS
        )

    def run(self, tmp=None, task_vars=None):
        result = super(ActionModule, self).run(tmp, task_vars or {})
        left = self.template(self._task.args['left'])
        right = self.template(self._task.args['right'])

        diff = text_diff(left, right)
        if diff is None:
            return {
                'changed': False
            }

        return {
            'changed': False,
            'failed': True,
            'msg': diff,
            '_ansible_verbose_always': True,
        }
