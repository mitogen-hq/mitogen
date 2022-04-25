"""
Arrange for all ContextService connections to be torn down unconditionally,
required for reliable LRU tests.
"""

import ansible_mitogen.connection
import ansible_mitogen.services

from ansible.plugins.action import ActionBase


class ActionModule(ActionBase):
    # Running this for every host is pointless.
    BYPASS_HOST_LOOP = True

    def run(self, tmp=None, task_vars=None):
        if not isinstance(self._connection,
                          ansible_mitogen.connection.Connection):
            return {
                'skipped': True,
            }

        self._connection._connect()
        binding = self._connection.get_binding()
        return {
            'changed': True,
            'result': binding.get_service_context().call_service(
                service_name='ansible_mitogen.services.ContextService',
                method_name='shutdown_all',
            )
        }
