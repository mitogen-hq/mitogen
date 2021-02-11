# coding: utf-8
# Copyright 2018, Yannig Perré
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

from __future__ import absolute_import
import os.path
import sys

from ansible.errors import AnsibleConnectionFailure
from ansible.module_utils.six import iteritems

try:
    import ansible_mitogen
except ImportError:
    base_dir = os.path.dirname(__file__)
    sys.path.insert(0, os.path.abspath(os.path.join(base_dir, '../../..')))
    del base_dir

import ansible_mitogen.connection
import ansible_mitogen.loaders


_get_result = ansible_mitogen.loaders.connection_loader__get(
    'kubectl',
    class_only=True,
)


class Connection(ansible_mitogen.connection.Connection):
    transport = 'kubectl'

    not_supported_msg = (
        'The "mitogen_kubectl" plug-in requires a version of Ansible '
        'that ships with the "kubectl" connection plug-in.'
    )

    def __init__(self, *args, **kwargs):
        if not _get_result:
            raise AnsibleConnectionFailure(self.not_supported_msg)
        super(Connection, self).__init__(*args, **kwargs)

    def get_extra_args(self):
        try:
            # Ansible < 2.10, _get_result is the connection class
            connection_options = _get_result.connection_options
        except AttributeError:
            # Ansible >= 2.10, _get_result is a get_with_context_result
            connection_options = _get_result.object.connection_options
        parameters = []
        for key, option in iteritems(connection_options):
            if self.get_task_var('ansible_' + key) is not None:
                parameters += [ option, self.get_task_var('ansible_' + key) ]

        return parameters
