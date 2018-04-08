# Copyright 2017, David Wilson
#
# Redistribution and use in source and binary forms, with or without
# modification, are permitted provided that the following conditions are met:
#
# 1. Redistributions of source code must retain the above copyright notice,
# this list of conditions and the following disclaimer.
#
# 2. Redistributions in binary form must reproduce the above copyright notice,
# this list of conditions and the following disclaimer in the documentation
# and/or other materials provided with the distribution.
#
# 3. Neither the name of the copyright holder nor the names of its contributors
# may be used to endorse or promote products derived from this software without
# specific prior written permission.
#
# THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS"
# AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE
# IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE
# ARE DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT HOLDER OR CONTRIBUTORS BE
# LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR
# CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF
# SUBSTITUTE GOODS OR SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS
# INTERRUPTION) HOWEVER CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN
# CONTRACT, STRICT LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE)
# ARISING IN ANY WAY OUT OF THE USE OF THIS SOFTWARE, EVEN IF ADVISED OF THE
# POSSIBILITY OF SUCH DAMAGE.

import ansible.plugins.action
import mitogen.core
import mitogen.utils
import ansible_mitogen.services
import ansible_mitogen.target


class ActionModule(ansible.plugins.action.ActionBase):
    def _get_async_result(self, job_id):
        self._connection._connect()
        return mitogen.service.call(
            context=self._connection.parent,
            handle=ansible_mitogen.services.JobResultService.handle,
            method='get',
            kwargs={
                'job_id': job_id,
            }
        )

    def _on_result_pending(self, job_id):
        return {
            '_ansible_parsed': True,
            'ansible_job_id': job_id,
            'started': 1,
            'failed': 0,
            'finished': 0,
            'msg': '',
        }

    def _on_result_available(self, job_id, result):
        dct = self._parse_returned_data(result)
        dct['ansible_job_id'] = job_id
        dct['started'] = 1
        dct['finished'] = 1

        # Cutpasted from the action.py.
        if 'stdout' in dct and 'stdout_lines' not in dct:
            dct['stdout_lines'] = (dct['stdout'] or u'').splitlines()
        if 'stderr' in dct and 'stderr_lines' not in dct:
            dct['stderr_lines'] = (dct['stderr'] or u'').splitlines()
        return dct

    def run(self, tmp=None, task_vars=None):
        job_id = mitogen.utils.cast(self._task.args['jid'])

        result = self._get_async_result(job_id)
        if result is None:
            return self._on_result_pending(job_id)
        else:
            return self._on_result_available(job_id, result)
