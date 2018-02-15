# Copyright 2017, David Wilson
#
# Redistribution and use in source and binary forms, with or without
# modification, are permitted provided that the following conditions are met:
#
# 1. Redistributions of source code must retain the above copyright notice, this
# list of conditions and the following disclaimer.
#
# 2. Redistributions in binary form must reproduce the above copyright notice,
# this list of conditions and the following disclaimer in the documentation
# and/or other materials provided with the distribution.
#
# 3. Neither the name of the copyright holder nor the names of its contributors
# may be used to endorse or promote products derived from this software without
# specific prior written permission.
#
# THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS" AND
# ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE IMPLIED
# WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE
# DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT HOLDER OR CONTRIBUTORS BE LIABLE
# FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL
# DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR
# SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER
# CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY,
# OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE
# OF THIS SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.

from __future__ import absolute_import
import os

import ansible
import ansible.plugins
import mitogen.core


def cast(obj):
    """
    Ansible loves to decorate built-in types to implement useful functionality
    like Vault, however cPickle loves to preserve those decorations during
    serialization, resulting in CallError.

    So here we recursively undecorate `obj`, ensuring that any instances of
    subclasses of built-in types are downcast to the base type.
    """
    if isinstance(obj, dict):
        return {cast(k): cast(v) for k, v in obj.iteritems()}
    if isinstance(obj, (list, tuple)):
        return [cast(v) for v in obj]
    if obj is None or isinstance(obj, (int, float)):
        return obj
    if isinstance(obj, unicode):
        return unicode(obj)
    if isinstance(obj, str):
        return str(obj)
    if isinstance(obj, (mitogen.core.Context,
                        mitogen.core.Dead,
                        mitogen.core.CallError)):
        return obj
    raise TypeError("Cannot serialize: %r: %r" % (type(obj), obj))


def get_command_module_name(module_name):
    """
    Given the name of an Ansible command module, return its canonical module
    path within the ansible.

    :param module_name:
        "shell"
    :return: 
        "ansible.modules.commands.shell"
    """
    path = ansible.plugins.module_loader.find_plugin(module_name, '')
    relpath = os.path.relpath(path, os.path.dirname(ansible.__file__))
    root, _ = os.path.splitext(relpath)
    return 'ansible.' + root.replace('/', '.')
