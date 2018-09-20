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

import logging

import mitogen.core
import mitogen.parent

import ansible.plugins.connection.kubectl

from ansible.module_utils.six import iteritems

LOG = logging.getLogger(__name__)

class Stream(mitogen.parent.Stream):
    child_is_immediate_subprocess = True

    pod = None
    container = None
    username = None
    kubectl_path = 'kubectl'
    kubectl_options = []

    # TODO: better way of capturing errors such as "No such container."
    create_child_args = {
        'merge_stdio': True
    }

    def construct(self, pod = None, kubectl_path=None,
                  additional_parameters=None, **kwargs):
        assert(pod)
        super(Stream, self).construct(**kwargs)

        self.kubectl_options = additional_parameters
        self.pod = pod

    def connect(self):
        super(Stream, self).connect()
        self.name = u'kubectl.' + (self.pod) + str(self.container) + str(self.kubectl_options)

    def get_boot_command(self):
        bits = [self.kubectl_path] + self.kubectl_options + ['exec', '-it', self.pod]

        return bits + [ "--" ] + super(Stream, self).get_boot_command()
