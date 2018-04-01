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
import logging
import os.path
import zlib

import mitogen
import mitogen.service


LOG = logging.getLogger(__name__)


class ContextService(mitogen.service.DeduplicatingService):
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

    :returns tuple:
        Tuple of `(context, home_dir)`, where:
            * `context` is the mitogen.master.Context referring to the target
              context.
            * `home_dir` is a cached copy of the remote directory.

    mitogen.master.Context:
        Corresponding Context instance.
    """
    handle = 500
    max_message_size = 1000
    required_args = {
        'method': str
    }

    def get_response(self, args):
        args.pop('discriminator', None)
        method = getattr(self.router, args.pop('method'))
        context = method(**args)
        home_dir = context.call(os.path.expanduser, '~')
        return context, home_dir


class FileService(mitogen.service.Service):
    """
    Primitive latency-inducing file server for old-style incantations of the
    module runner. This is to be replaced later with a scheme that forwards
    files known to be missing without the target having to ask for them,
    avoiding a corresponding roundtrip per file.

    Paths must be explicitly added to the service by a trusted context before
    they will be served to an untrusted context.

    :param tuple args:
        Tuple of `(cmd, path)`, where:
            - cmd: one of "register", "fetch", where:
                - register: register a file that may be fetched
                - fetch: fetch a file that was previously registered
            - path: key of the file to fetch or register

    :returns:
        Returns ``None` for "register", or the file data for "fetch".

    :raises mitogen.core.CallError:
        Security violation occurred, either path not registered, or attempt to
        register path from unprivileged context.
    """
    handle = 501
    max_message_size = 1000
    policies = (
        mitogen.service.AllowAny(),
    )

    unprivileged_msg = 'Cannot register from unprivileged context.'
    unregistered_msg = 'Path is not registered with FileService.'

    def __init__(self, router):
        super(FileService, self).__init__(router)
        self._paths = {}

    def validate_args(self, args):
        return (
            isinstance(args, tuple) and
            len(args) == 2 and
            args[0] in ('register', 'fetch') and
            isinstance(args[1], str)
        )

    def dispatch(self, args, msg):
        cmd, path = msg
        return getattr(self, cmd)(path, msg)

    def register(self, path, msg):
        if not mitogen.core.has_parent_authority(msg):
            raise mitogen.core.CallError(self.unprivileged_msg)

        with open(path, 'rb') as fp:
            self._paths[path] = zlib.compress(fp.read())

    def fetch(self, path, msg):
        if path not in self._paths:
            raise mitogen.core.CallError(self.unregistered_msg)

        LOG.debug('Serving %r to context %r', path, msg.src_id)
        return self._paths[path]
