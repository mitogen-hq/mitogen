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
These classes implement execution for each style of Ansible module. They are
instantiated in the target context by way of helpers.py::run_module().

Each class in here has a corresponding Planner class in planners.py that knows
how to build arguments for it, preseed related data, etc.
"""

from __future__ import absolute_import
import cStringIO
import json
import logging
import os
import sys
import tempfile
import types

import ansible_mitogen.helpers  # TODO: circular import

try:
    from shlex import quote as shlex_quote
except ImportError:
    from pipes import quote as shlex_quote

# Prevent accidental import of an Ansible module from hanging on stdin read.
import ansible.module_utils.basic
ansible.module_utils.basic._ANSIBLE_ARGS = '{}'


LOG = logging.getLogger(__name__)


def reopen_readonly(fp):
    """
    Replace the file descriptor belonging to the file object `fp` with one
    open on the same file (`fp.name`), but opened with :py:data:`os.O_RDONLY`.
    This enables temporary files to be executed on Linux, which usually theows
    ``ETXTBUSY`` if any writeable handle exists pointing to a file passed to
    `execve()`.
    """
    fd = os.open(fp.name, os.O_RDONLY)
    os.dup2(fd, fp.fileno())
    os.close(fd)


class Runner(object):
    """
    Ansible module runner. After instantiation (with kwargs supplied by the
    corresponding Planner), `.run()` is invoked, upon which `setup()`,
    `_run()`, and `revert()` are invoked, with the return value of `_run()`
    returned by `run()`.

    Subclasses may override `_run`()` and extend `setup()` and `revert()`.
    """
    def __init__(self, module, raw_params=None, args=None, env=None):
        if args is None:
            args = {}
        if raw_params is not None:
            args['_raw_params'] = raw_params

        self.module = module
        self.raw_params = raw_params
        self.args = args
        self.env = env

    def setup(self):
        """
        Prepare the current process for running a module. The base
        implementation simply prepares the environment.
        """
        self._env = TemporaryEnvironment(self.env)

    def revert(self):
        """
        Revert any changes made to the process after running a module. The base
        implementation simply restores the original environment.
        """
        self._env.revert()

    def _run(self):
        """
        The _run() method is expected to return a dictionary in the form of
        ActionBase._low_level_execute_command() output, i.e. having::

            {
                "rc": int,
                "stdout": "stdout data",
                "stderr": "stderr data"
            }
        """
        raise NotImplementedError()

    def run(self):
        """
        Set up the process environment in preparation for running an Ansible
        module. This monkey-patches the Ansible libraries in various places to
        prevent it from trying to kill the process on completion, and to
        prevent it from reading sys.stdin.

        :returns:
            Module result dictionary.
        """
        self.setup()
        try:
            return self._run()
        finally:
            self.revert()


class TemporaryEnvironment(object):
    def __init__(self, env=None):
        self.original = os.environ.copy()
        self.env = env or {}
        os.environ.update((k, str(v)) for k, v in self.env.iteritems())

    def revert(self):
        os.environ.clear()
        os.environ.update(self.original)


class TemporaryArgv(object):
    def __init__(self, argv):
        self.original = sys.argv[:]
        sys.argv[:] = argv

    def revert(self):
        sys.argv[:] = self.original


class NewStyleStdio(object):
    """
    Patch ansible.module_utils.basic argument globals.
    """
    def __init__(self, args):
        self.original_stdout = sys.stdout
        self.original_stderr = sys.stderr
        self.original_stdin = sys.stdin
        sys.stdout = cStringIO.StringIO()
        sys.stderr = cStringIO.StringIO()
        ansible.module_utils.basic._ANSIBLE_ARGS = json.dumps({
            'ANSIBLE_MODULE_ARGS': args
        })
        sys.stdin = cStringIO.StringIO(
            ansible.module_utils.basic._ANSIBLE_ARGS
        )

    def revert(self):
        sys.stdout = self.original_stdout
        sys.stderr = self.original_stderr
        sys.stdin = self.original_stdin
        ansible.module_utils.basic._ANSIBLE_ARGS = '{}'


class ProgramRunner(Runner):
    def __init__(self, path, service_context, **kwargs):
        super(ProgramRunner, self).__init__(**kwargs)
        self.path = path
        self.service_context = service_context

    def setup(self):
        super(ProgramRunner, self).setup()
        self._setup_program()

    def _setup_program(self):
        """
        Create a temporary file containing the program code. The code is
        fetched via :meth:`_get_program`.
        """
        self.program_fp = tempfile.NamedTemporaryFile(
            prefix='ansible_mitogen',
            suffix='-binary',
        )
        self.program_fp.write(self._get_program())
        self.program_fp.flush()
        os.chmod(self.program_fp.name, int('0700', 8))
        reopen_readonly(self.program_fp)

    def _get_program(self):
        """
        Fetch the module binary from the master if necessary.
        """
        return ansible_mitogen.helpers.get_file(
            context=self.service_context,
            path=self.path,
        )

    def _get_program_args(self):
        return [
            self.args['_ansible_shell_executable'],
            '-c',
            self.program_fp.name
        ]

    def revert(self):
        """
        Delete the temporary program file.
        """
        super(ProgramRunner, self).revert()
        self.program_fp.close()

    def _run(self):
        try:
            rc, stdout, stderr = ansible_mitogen.helpers.exec_args(
                args=self._get_program_args(),
            )
        except Exception, e:
            LOG.exception('While running %s', self._get_program_args())
            return {
                'rc': 1,
                'stdout': '',
                'stderr': '%s: %s' % (type(e), e),
            }

        return {
            'rc': rc,
            'stdout': stdout,
            'stderr': stderr
        }


class ArgsFileRunner(Runner):
    def setup(self):
        super(ArgsFileRunner, self).setup()
        self._setup_args()

    def _setup_args(self):
        """
        Create a temporary file containing the module's arguments. The
        arguments are formatted via :meth:`_get_args`.
        """
        self.args_fp = tempfile.NamedTemporaryFile(
            prefix='ansible_mitogen',
            suffix='-args',
        )
        self.args_fp.write(self._get_args_contents())
        self.args_fp.flush()
        reopen_readonly(self.program_fp)

    def _get_args_contents(self):
        """
        Return the module arguments formatted as JSON.
        """
        return json.dumps(self.args)

    def _get_program_args(self):
        return [
            self.args['_ansible_shell_executable'],
            '-c',
            "%s %s" % (self.program_fp.name, self.args_fp.name),
        ]

    def revert(self):
        """
        Delete the temporary argument file.
        """
        super(ArgsFileRunner, self).revert()
        self.args_fp.close()


class BinaryRunner(ArgsFileRunner, ProgramRunner):
    pass


class ScriptRunner(ProgramRunner):
    def __init__(self, interpreter, interpreter_arg, **kwargs):
        super(ScriptRunner, self).__init__(**kwargs)
        self.interpreter = interpreter
        self.interpreter_arg = interpreter_arg

    b_ENCODING_STRING = b'# -*- coding: utf-8 -*-'

    def _get_program(self):
        return self._rewrite_source(
            super(ScriptRunner, self)._get_program()
        )

    def _rewrite_source(self, s):
        """
        Mutate the source according to the per-task parameters.
        """
        # Couldn't find shebang, so let shell run it, because shell assumes
        # executables like this are just shell scripts.
        if not self.interpreter:
            return s

        shebang = '#!' + self.interpreter
        if self.interpreter_arg:
            shebang += ' ' + self.interpreter_arg

        new = [shebang]
        if os.path.basename(self.interpreter).startswith('python'):
            new.append(self.b_ENCODING_STRING)

        _, _, rest = s.partition('\n')
        new.append(rest)
        return '\n'.join(new)


class NewStyleRunner(ScriptRunner):
    """
    Execute a new-style Ansible module, where Module Replacer-related tricks
    aren't required.
    """
    #: path => new-style module bytecode.
    _code_by_path = {}

    def setup(self):
        super(NewStyleRunner, self).setup()
        self._stdio = NewStyleStdio(self.args)
        self._argv = TemporaryArgv([self.path])

    def revert(self):
        self._argv.revert()
        self._stdio.revert()
        super(NewStyleRunner, self).revert()

    def _get_code(self):
        try:
            return self._code_by_path[self.path]
        except KeyError:
            return self._code_by_path.setdefault(self.path, compile(
                source=ansible_mitogen.helpers.get_file(
                    context=self.service_context,
                    path=self.path,
                ),
                filename=self.path,
                mode='exec',
                dont_inherit=True,
            ))

    def _run(self):
        code = self._get_code()
        mod = types.ModuleType('__main__')
        d = vars(mod)
        e = None

        try:
            exec code in d, d
        except SystemExit, e:
            pass

        return {
            'rc': e[0] if e else 2,
            'stdout': sys.stdout.getvalue(),
            'stderr': sys.stderr.getvalue(),
        }


class JsonArgsRunner(ScriptRunner):
    JSON_ARGS = '<<INCLUDE_ANSIBLE_MODULE_JSON_ARGS>>'

    def _get_args_contents(self):
        return json.dumps(self.args)

    def _rewrite_source(self, s):
        return (
            super(JsonArgsRunner, self)._rewrite_source(s)
            .replace(self.JSON_ARGS, self._get_args_contents())
        )


class WantJsonRunner(ArgsFileRunner, ScriptRunner):
    pass


class OldStyleRunner(ArgsFileRunner, ScriptRunner):
    def _get_args_contents(self):
        """
        Mimic the argument formatting behaviour of
        ActionBase._execute_module().
        """
        return ' '.join(
            '%s=%s' % (key, shlex_quote(str(self.args[key])))
            for key in self.args
        ) + ' '  # Bug-for-bug :(
