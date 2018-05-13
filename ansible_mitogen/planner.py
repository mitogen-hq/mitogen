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
import ansible.module_utils

try:
    from ansible.plugins.loader import module_loader
    from ansible.plugins.loader import module_utils_loader
except ImportError:  # Ansible <2.4
    from ansible.plugins import module_loader
    from ansible.plugins import module_utils_loader

import mitogen
import mitogen.service
import ansible_mitogen.target
import ansible_mitogen.services


LOG = logging.getLogger(__name__)
NO_METHOD_MSG = 'Mitogen: no invocation method found for: '
NO_INTERPRETER_MSG = 'module (%s) is missing interpreter line'


def parse_script_interpreter(source):
    """
    Extract the script interpreter and its sole argument from the module
    source code.

    :returns:
        Tuple of `(interpreter, arg)`, where `intepreter` is the script
        interpreter and `arg` is its sole argument if present, otherwise
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
    target.run_module() or helpers.run_module_async() in the target context.
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
        """
        Return true if the supplied `invocation` matches the module type
        implemented by this planner.
        """
        raise NotImplementedError()

    def get_should_fork(self, invocation):
        """
        Asynchronous tasks must always be forked.
        """
        return invocation.wrap_async

    def plan(self, invocation, **kwargs):
        """
        If :meth:`detect` returned :data:`True`, plan for the module's
        execution, including granting access to or delivering any files to it
        that are known to be absent, and finally return a dict::

            {
                # Name of the class from runners.py that implements the
                # target-side execution of this module type.
                "runner_name": "...",

                # Remaining keys are passed to the constructor of the class
                # named by `runner_name`.
            }
        """
        kwargs.setdefault('emulate_tty', True)
        kwargs.setdefault('service_context', invocation.connection.parent)
        kwargs.setdefault('should_fork', self.get_should_fork(invocation))
        kwargs.setdefault('wrap_async', invocation.wrap_async)
        return kwargs

    def __repr__(self):
        return '%s()' % (type(self).__name__,)


class BinaryPlanner(Planner):
    """
    Binary modules take their arguments and will return data to Ansible in the
    same way as want JSON modules.
    """
    runner_name = 'BinaryRunner'

    def detect(self, invocation):
        return module_common._is_binary(invocation.module_source)

    def _grant_file_service_access(self, invocation):
        invocation.connection._connect()
        mitogen.service.call(
            context=invocation.connection.parent,
            handle=ansible_mitogen.services.FileService.handle,
            method='register',
            kwargs={
                'path': invocation.module_path
            }
        )

    def plan(self, invocation, **kwargs):
        self._grant_file_service_access(invocation)
        return super(BinaryPlanner, self).plan(
            invocation=invocation,
            runner_name=self.runner_name,
            module=invocation.module_name,
            path=invocation.module_path,
            args=invocation.module_args,
            env=invocation.env,
            **kwargs
        )


class ScriptPlanner(BinaryPlanner):
    """
    Common functionality for script module planners -- handle interpreter
    detection and rewrite.
    """
    def _get_interpreter(self, invocation):
        interpreter, arg = parse_script_interpreter(invocation.module_source)
        if interpreter is None:
            raise ansible.errors.AnsibleError(NO_INTERPRETER_MSG % (
                invocation.module_name,
            ))

        key = u'ansible_%s_interpreter' % os.path.basename(interpreter).strip()
        try:
            template = invocation.task_vars[key].strip()
            return invocation.templar.template(template), arg
        except KeyError:
            return interpreter, arg

    def plan(self, invocation, **kwargs):
        interpreter, arg = self._get_interpreter(invocation)
        return super(ScriptPlanner, self).plan(
            invocation=invocation,
            interpreter_arg=arg,
            interpreter=interpreter,
            **kwargs
        )


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

    def _get_interpreter(self, invocation):
        return None, None

    def _grant_file_service_access(self, invocation):
        """
        Stub out BinaryPlanner's method since ModuleDepService makes internal
        calls to grant file access, avoiding 2 IPCs per task invocation.
        """

    def get_should_fork(self, invocation):
        """
        In addition to asynchronous tasks, new-style modules should be forked
        if mitogen_task_isolation=fork.
        """
        return (
            super(NewStylePlanner, self).get_should_fork(invocation) or
            (invocation.task_vars.get('mitogen_task_isolation') == 'fork')
        )

    def detect(self, invocation):
        return 'from ansible.module_utils.' in invocation.module_source

    def get_module_utils_path(self, invocation):
        paths = [
            path
            for path in module_utils_loader._get_paths(subdirs=False)
            if os.path.isdir(path)
        ]
        paths.append(module_common._MODULE_UTILS_PATH)
        return tuple(paths)

    def get_module_utils(self, invocation):
        invocation.connection._connect()
        module_utils = mitogen.service.call(
            context=invocation.connection.parent,
            handle=ansible_mitogen.services.ModuleDepService.handle,
            method='scan',
            kwargs={
                'module_name': 'ansible_module_%s' % (invocation.module_name,),
                'module_path': invocation.module_path,
                'search_path': self.get_module_utils_path(invocation),
            }
        )
        modutils_dir = os.path.dirname(ansible.module_utils.__file__)
        has_custom = not all(path.startswith(modutils_dir)
                             for fullname, path, is_pkg in module_utils)
        return module_utils, has_custom

    def plan(self, invocation):
        module_utils, has_custom = self.get_module_utils(invocation)
        return super(NewStylePlanner, self).plan(
            invocation,
            module_utils=module_utils,
            should_fork=(self.get_should_fork(invocation) or has_custom),
        )


class ReplacerPlanner(NewStylePlanner):
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
            LOG.debug('%r accepted %r (filename %r)', planner,
                      invocation.module_name, invocation.module_path)
            return invocation.action._postprocess_response(
                invocation.connection.call(
                    ansible_mitogen.target.run_module,
                    planner.plan(invocation),
                )
            )
        LOG.debug('%r rejected %r', planner, invocation.module_name)

    raise ansible.errors.AnsibleError(NO_METHOD_MSG + repr(invocation))
