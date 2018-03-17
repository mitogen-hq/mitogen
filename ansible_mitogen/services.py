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

from __future__ import absolute_import
import mitogen.service


class ContextService(mitogen.service.Service):
    """
    Used by worker processes connecting back into the top-level process to
    fetch the single Context instance corresponding to the supplied connection
    configuration, creating a matching connection if it does not exist.

    For connection methods and their parameters, refer to:
        https://mitogen.readthedocs.io/en/latest/api.html#context-factories

    This concentrates all SSH connections in the top-level process, which may
    become a bottleneck. There are multiple ways to fix that: 
        * creating one .local() child context per CPU and sharding connections
          between them, using the master process to route messages, or
        * as above, but having each child create a unique UNIX listener and
          having workers connect in directly.

    :param dict dct:
        Parameters passed to `mitogen.master.Router.[method]()`.

        * The `method` key is popped from the dictionary and used to look up
          the Mitogen connection method.
        * The `discriminator` key is mixed into the key used to select an
          existing connection, but popped from the list of arguments passed to
          the connection method.

    :returns mitogen.master.Context:
        Corresponding Context instance.
    """
    handle = 500
    max_message_size = 1000

    def __init__(self, router):
        super(ContextService, self).__init__(router)
        self._context_by_key = {}

    def validate_args(self, args):
        return isinstance(args, dict)

    def dispatch(self, dct, msg):
        key = repr(sorted(dct.items()))
        dct.pop('discriminator', None)

        if key not in self._context_by_key:
            method = getattr(self.router, dct.pop('method'))
            self._context_by_key[key] = method(**dct)
        return self._context_by_key[key]

