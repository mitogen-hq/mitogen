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

"""
Classes to detect each case from [0] and prepare arguments necessary for the
corresponding Runner class within the target, including preloading requisite
files/modules known missing.

[0] "Ansible Module Architecture", developing_program_flow_modules.html
"""

from __future__ import absolute_import
import logging
import os

from ansible.executor import module_common
import ansible.errors

try:
    from ansible.plugins.loader import module_loader
except ImportError:  # Ansible <2.4
    from ansible.plugins import module_loader

import mitogen
import mitogen.service
import ansible_mitogen.helpers


LOG = logging.getLogger(__name__)


class Invocation(object):
    """
    Collect up a module's execution environment then use it to invoke
    helpers.run_module() or helpers.run_module_async() in the target context.
    """
    def __init__(self, action, connection, module_name, module_args,
                 task_vars, tmp, env, wrap_async):
        #: Instance of the ActionBase subclass invoking the module. Required to
        #: access some output postprocessing methods that don't belong in
        #: ActionBase at all.
        self.action = action
        self.connection = connection
        self.module_name = module_name
        self.module_args = module_args
        self.module_path = None
        self.module_source = None
        self.task_vars = task_vars
        self.tmp = tmp
        self.env = env
        self.wrap_async = wrap_async

    def __repr__(self):
        return 'Invocation(module_name=%s)' % (self.module_name,)


class Planner(object):
    """
    A Planner receives a module name and the contents of its implementation
    file, indicates whether or not it understands how to run the module, and
    exports a method to run the module.
    """
    def detect(self, invocation):
        raise NotImplementedError()

    def plan(self, invocation):
        raise NotImplementedError()


class JsonArgsPlanner(Planner):
    """
    Script that has its interpreter directive and the task arguments
    substituted into its source as a JSON string.
    """
    def detect(self, invocation):
        return module_common.REPLACER_JSONARGS in invocation.module_source

    def plan(self, invocation):
        path = None  # TODO
        mitogen.service.call(501, ('register', path))
        return {
            'func': 'run_json_args_module',
            'binary': source,
            'args': args,
            'env': env,
        }


class WantJsonPlanner(Planner):
    """
    If a module has the string WANT_JSON in it anywhere, Ansible treats it as a
    non-native module that accepts a filename as its only command line
    parameter. The filename is for a temporary file containing a JSON string
    containing the module's parameters. The module needs to open the file, read
    and parse the parameters, operate on the data, and print its return data as
    a JSON encoded dictionary to stdout before exiting.

    These types of modules are self-contained entities. As of Ansible 2.1,
    Ansible only modifies them to change a shebang line if present.
    """
    def detect(self, invocation):
        return 'WANT_JSON' in invocation.module_source

    def plan(self, name, source, args, env):
        return {
            'func': 'run_want_json_module',
            'binary': source,
            'args': args,
            'env': env,
        }


class ReplacerPlanner(Planner):
    """
    The Module Replacer framework is the original framework implementing
    new-style modules. It is essentially a preprocessor (like the C
    Preprocessor for those familiar with that programming language). It does
    straight substitutions of specific substring patterns in the module file.
    There are two types of substitutions.

    * Replacements that only happen in the module file. These are public
      replacement strings that modules can utilize to get helpful boilerplate
      or access to arguments.

      "from ansible.module_utils.MOD_LIB_NAME import *" is replaced with the
      contents of the ansible/module_utils/MOD_LIB_NAME.py. These should only
      be used with new-style Python modules.

      "#<<INCLUDE_ANSIBLE_MODULE_COMMON>>" is equivalent to
      "from ansible.module_utils.basic import *" and should also only apply to
      new-style Python modules.

      "# POWERSHELL_COMMON" substitutes the contents of
      "ansible/module_utils/powershell.ps1". It should only be used with
      new-style Powershell modules.
    """
    def detect(self, invocation):
        return module_common.REPLACER in invocation.module_source

    def plan(self, name, source, args, env):
        return {
            'func': 'run_replacer_module',
            'binary': source,
            'args': args,
            'env': env,
        }


class BinaryPlanner(Planner):
    """
    Binary modules take their arguments and will return data to Ansible in the
    same way as want JSON modules.
    """
    def detect(self, invocation):
        return module_common._is_binary(invocation.module_source)

    def plan(self, name, source, args, env):
        return {
            'runner_name': 'BinaryRunner',
            'binary': source,
            'args': args,
            'env': env,
        }


class NativePlanner(Planner):
    """
    The Ansiballz framework differs from module replacer in that it uses real
    Python imports of things in ansible/module_utils instead of merely
    preprocessing the module.
    """
    def detect(self, invocation):
        return True

    def get_command_module_name(self, module_name):
        """
        Given the name of an Ansible command module, return its canonical
        module path within the ansible.

        :param module_name:
            "shell"
        :return:
            "ansible.modules.commands.shell"
        """
        path = module_loader.find_plugin(module_name, '')
        relpath = os.path.relpath(path, os.path.dirname(ansible.__file__))
        root, _ = os.path.splitext(relpath)
        return 'ansible.' + root.replace('/', '.')

    def plan(self, invocation):
        return {
            'runner_name': 'NativeRunner',
            'module': invocation.module_name,
            'mod_name': self.get_command_module_name(invocation.module_name),
            'args': invocation.module_args,
            'env': invocation.env,
        }


_planners = [
    # JsonArgsPlanner,
    # WantJsonPlanner,
    # ReplacerPlanner,
    BinaryPlanner,
    NativePlanner,
]


NO_METHOD_MSG = 'Mitogen: no invocation method found for: '
CRASHED_MSG = 'Mitogen: internal error: '


def get_module_data(name):
    path = module_loader.find_plugin(name, '')
    with open(path, 'rb') as fp:
        source = fp.read()
    return path, source


def invoke(invocation):
    """
    Find a suitable Planner that knows how to run `invocation`.
    """
    (invocation.module_path,
     invocation.module_source) = get_module_data(invocation.module_name)

    for klass in _planners:
        planner = klass()
        if planner.detect(invocation):
            break
    else:
        raise ansible.errors.AnsibleError(NO_METHOD_MSG + repr(invocation))

    kwargs = planner.plan(invocation)
    if invocation.wrap_async:
        helper = ansible_mitogen.helpers.run_module_async
    else:
        helper = ansible_mitogen.helpers.run_module

    try:
        js = invocation.connection.call(helper, kwargs)
    except mitogen.core.CallError as e:
        LOG.exception('invocation crashed: %r', invocation)
        summary = str(e).splitlines()[0]
        raise ansible.errors.AnsibleInternalError(CRASHED_MSG + summary)

    return invocation.action._postprocess_response(js)
