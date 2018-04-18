"""
Arrange for all ContextService connections to be torn down unconditionally,
required for reliable LRU tests.
"""

import traceback
import sys

import ansible_mitogen.services
import mitogen.service

from ansible.plugins.strategy import StrategyBase
from ansible.plugins.action import ActionBase


class ActionModule(ActionBase):
    def run(self, tmp=None, task_vars=None):
        if not type(self._connection).__module__.startswith('ansible_mitogen'):
            return {
                'changed': False
            }

        self._connection._connect()
        return {
            'changed': True,
            'result': mitogen.service.call(
                context=self._connection.parent,
                handle=ansible_mitogen.services.ContextService.handle,
                method='shutdown_all',
                kwargs={}
            )
        }
