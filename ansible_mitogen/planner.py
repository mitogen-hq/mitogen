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
import ansible_mitogen.services


LOG = logging.getLogger(__name__)


def parse_script_interpreter(source):
    """
    Extract the script interpreter and its sole argument from the module
    source code.

    :returns:
        Tuple of `(interpreter, arg)`, where `intepreter` is the script
        interpreter and `arg` is its solve argument if present, otherwise
        :py:data:`None`.
    """
    # Linux requires first 2 bytes with no whitespace, pretty sure it's the
    # same everywhere. See binfmt_script.c.
    if not source.startswith('#!'):
        return None, None

    # Find terminating newline. Assume last byte of binprm_buf if absent.
    nl = source.find('\n', 0, 128)
    if nl == -1:
        nl = min(128, len(source))

    # Split once on the first run of whitespace. If no whitespace exists,
    # bits just contains the interpreter filename.
    bits = source[2:nl].strip().split(None, 1)
    if len(bits) == 1:
        return bits[0], None
    return bits[0], bits[1]


class Invocation(object):
    """
    Collect up a module's execution environment then use it to invoke
    helpers.run_module() or helpers.run_module_async() in the target context.
    """
    def __init__(self, action, connection, module_name, module_args,
                 task_vars, templar, env, wrap_async):
        #: ActionBase instance invoking the module. Required to access some
        #: output postprocessing methods that don't belong in ActionBase at
        #: all.
        self.action = action
        #: Ansible connection to use to contact the target. Must be an
        #: ansible_mitogen connection.
        self.connection = connection
        #: Name of the module ('command', 'shell', etc.) to execute.
        self.module_name = module_name
        #: Final module arguments.
        self.module_args = module_args
        #: Task variables, needed to extract ansible_*_interpreter.
        self.task_vars = task_vars
        #: Templar, needed to extract ansible_*_interpreter.
        self.templar = templar
        #: Final module environment.
        self.env = env
        #: Boolean, if :py:data:`True`, launch the module asynchronously.
        self.wrap_async = wrap_async

        #: Initially ``None``, but set by :func:`invoke`. The path on the
        #: master to the module's implementation file.
        self.module_path = None
        #: Initially ``None``, but set by :func:`invoke`. The raw source or
        #: binary contents of the module.
        self.module_source = None

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


class BinaryPlanner(Planner):
    """
    Binary modules take their arguments and will return data to Ansible in the
    same way as want JSON modules.
    """
    runner_name = 'BinaryRunner'

    def detect(self, invocation):
        return module_common._is_binary(invocation.module_source)

    def plan(self, invocation):
        invocation.connection._connect()
        mitogen.service.call(
            invocation.connection.parent,
            ansible_mitogen.services.FileService.handle,
            ('register', invocation.module_path)
        )
        return {
            'runner_name': self.runner_name,
            'module': invocation.module_name,
            'service_context': invocation.connection.parent,
            'path': invocation.module_path,
            'args': invocation.module_args,
            'env': invocation.env,
        }


class ScriptPlanner(BinaryPlanner):
    """
    Common functionality for script module planners -- handle interpreter
    detection and rewrite.
    """
    def plan(self, invocation):
        kwargs = super(ScriptPlanner, self).plan(invocation)
        interpreter, arg = parse_script_interpreter(invocation.module_source)
        shebang, _ = module_common._get_shebang(
            interpreter=interpreter,
            task_vars=invocation.task_vars,
            templar=invocation.templar,
        )
        if shebang:
            interpreter = shebang[2:]

        kwargs['interpreter'] = interpreter
        kwargs['interpreter_arg'] = arg
        return kwargs


class ReplacerPlanner(BinaryPlanner):
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
    runner_name = 'ReplacerRunner'

    def detect(self, invocation):
        return module_common.REPLACER in invocation.module_source


class JsonArgsPlanner(ScriptPlanner):
    """
    Script that has its interpreter directive and the task arguments
    substituted into its source as a JSON string.
    """
    runner_name = 'JsonArgsRunner'

    def detect(self, invocation):
        return module_common.REPLACER_JSONARGS in invocation.module_source


class WantJsonPlanner(ScriptPlanner):
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
    runner_name = 'WantJsonRunner'

    def detect(self, invocation):
        return 'WANT_JSON' in invocation.module_source


class NewStylePlanner(ScriptPlanner):
    """
    The Ansiballz framework differs from module replacer in that it uses real
    Python imports of things in ansible/module_utils instead of merely
    preprocessing the module.
    """
    runner_name = 'NewStyleRunner'

    def detect(self, invocation):
        return 'from ansible.module_utils.' in invocation.module_source


class ReplacerPlanner(NewStylePlanner):
    runner_name = 'ReplacerRunner'

    def detect(self, invocation):
        return module_common.REPLACER in invocation.module_source


class OldStylePlanner(ScriptPlanner):
    runner_name = 'OldStyleRunner'

    def detect(self, invocation):
        # Everything else.
        return True


_planners = [
    BinaryPlanner,
    # ReplacerPlanner,
    NewStylePlanner,
    JsonArgsPlanner,
    WantJsonPlanner,
    OldStylePlanner,
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
