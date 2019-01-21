#
# Print data structure diff on assertion failure.
#
# assert_equal:  left=some.result right={1:2}
#

__metaclass__ = type

import unittest2

from ansible.errors import AnsibleError
from ansible.plugins.action import ActionBase
from ansible.module_utils.six import string_types


class TestCase(unittest2.TestCase):
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

    def run(self, tmp=None, task_vars=None):
        result = super(ActionModule, self).run(tmp, task_vars or {})

        left = self._templar.template(
            self._task.args['left'],
            convert_bare=True,
            bare_deprecated=False,
        )
        right = self._templar.template(self._task.args['right'],
            convert_bare=True,
            bare_deprecated=False,
        )

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
