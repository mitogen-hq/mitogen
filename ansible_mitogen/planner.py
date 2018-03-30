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
This exists to detect every case defined in [0] and prepare arguments necessary
for the executor implementation running within the target, including preloading
any requisite files/Python modules known to be missing.

[0] "Ansible Module Architecture", developing_program_flow_modules.html
"""

from __future__ import absolute_import
from ansible.executor import module_common

import mitogen
import mitogen.service
import ansible_mitogen.helpers


class Planner(object):
    """
    A Planner receives a module name and the contents of its implementation
    file, indicates whether or not it understands how to run the module, and
    exports a method to run the module.
    """
    def detect(self, name, source):
        assert 0

    def run(self, connection, name, source, args, env):
        assert 0


class JsonArgsPlanner(Planner):
    """
    Script that has its interpreter directive and the task arguments
    substituted into its source as a JSON string.
    """
    def detect(self, name, source):
        return module_common.REPLACER_JSONARGS in source

    def run(self, name, source, args, env):
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
    containing the module’s parameters. The module needs to open the file, read
    and parse the parameters, operate on the data, and print its return data as
    a JSON encoded dictionary to stdout before exiting.

    These types of modules are self-contained entities. As of Ansible 2.1,
    Ansible only modifies them to change a shebang line if present.
    """
    def detect(self, name, source):
        return 'WANT_JSON' in source

    def run(self, name, source, args, env):
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
    def detect(self, name, source):
        return module_common.REPLACER in source

    def run(self, name, source, args, env):
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
    helper = staticmethod(ansible_mitogen.helpers.run_binary)

    def detect(self, name, source):
        return module_common._is_binary(source)

    def run(self, name, source, args, env):
        return {
            'func': 'run_binary_module',
            'binary': source,
            'args': args,
            'env': env,
        }


class PythonPlanner(Planner):
    """
    The Ansiballz framework differs from module replacer in that it uses real
    Python imports of things in ansible/module_utils instead of merely
    preprocessing the module.
    """
    helper = staticmethod(ansible_mitogen.helpers.run_module)

    def detect(self, name, source):
        return True

    def run(self, name, source, args, env):
        return {
            'func': 'run_python_module',
            'module': name,
            'args': args,
            'env': env
        }


_planners = [
    # JsonArgsPlanner,
    # WantJsonPlanner,
    # ReplacerPlanner,
    BinaryPlanner,
    PythonPlanner,
]


def plan():
    pass
