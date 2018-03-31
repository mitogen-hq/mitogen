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
import json
import os
import tempfile

import ansible_mitogen.helpers  # TODO: circular import

try:
    from shlex import quote as shlex_quote
except ImportError:
    from pipes import quote as shlex_quote

# Prevent accidental import of an Ansible module from hanging on stdin read.
import ansible.module_utils.basic
ansible.module_utils.basic._ANSIBLE_ARGS = '{}'


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


class NativeModuleExit(Exception):
    """
    Capture the result of a call to `.exit_json()` or `.fail_json()` by a
    native Ansible module.
    """
    def __init__(self, ansible_module, **kwargs):
        ansible_module.add_path_info(kwargs)
        kwargs.setdefault('invocation', {
            'module_args': ansible_module.params
        })
        ansible_module.do_cleanup_files()
        self.dct = ansible.module_utils.basic.remove_values(
            kwargs,
            ansible_module.no_log_values,
        )


class NativeMethodOverrides(object):
    @staticmethod
    def exit_json(self, **kwargs):
        """
        Raise exit_json() output as the `.dct` attribute of a
        :class:`NativeModuleExit` exception`.
        """
        kwargs.setdefault('changed', False)
        raise NativeModuleExit(self, **kwargs)

    @staticmethod
    def fail_json(self, **kwargs):
        """
        Raise fail_json() output as the `.dct` attribute of a
        :class:`NativeModuleExit` exception`.
        """
        kwargs.setdefault('failed', True)
        raise NativeModuleExit(self, **kwargs)

    klass = ansible.module_utils.basic.AnsibleModule

    def __init__(self):
        self._original_exit_json = self.klass.exit_json
        self._original_fail_json = self.klass.fail_json
        self.klass.exit_json = self.exit_json
        self.klass.fail_json = self.fail_json

    def revert(self):
        """
        Restore prior state.
        """
        self.klass.exit_json = self._original_exit_json
        self.klass.fail_json = self._original_fail_json


class NativeModuleArguments(object):
    """
    Patch ansible.module_utils.basic argument globals.
    """
    def __init__(self, args):
        self.original = ansible.module_utils.basic._ANSIBLE_ARGS
        ansible.module_utils.basic._ANSIBLE_ARGS = json.dumps({
            'ANSIBLE_MODULE_ARGS': args
        })

    def revert(self):
        """
        Restore prior state.
        """
        ansible.module_utils.basic._ANSIBLE_ARGS = self.original


class NativeRunner(Runner):
    """
    Execute a new-style Ansible module, where Module Replacer-related tricks
    aren't required.
    """
    def __init__(self, mod_name, **kwargs):
        super(NativeRunner, self).__init__(**kwargs)
        self.mod_name = mod_name

    def setup(self):
        super(NativeRunner, self).setup()
        self._overrides = NativeMethodOverrides()
        self._args = NativeModuleArguments(self.args)

    def revert(self):
        super(NativeRunner, self).revert()
        self._args.revert()
        self._overrides.revert()

    def _fixup__default(self, mod):
        pass

    def _fixup__yum_repository(self, mod):
        # https://github.com/dw/mitogen/issues/154
        mod.YumRepo.repofile = mod.configparser.RawConfigParser()

    def _run(self):
        fixup = getattr(self, '_fixup__' + self.module, self._fixup__default)
        try:
            mod = __import__(self.mod_name, {}, {}, [''])
            fixup(mod)
            # Ansible modules begin execution on import. Thus the above
            # __import__ will cause either Exit or ModuleError to be raised. If
            # we reach the line below, the module did not execute and must
            # already have been imported for a previous invocation, so we need
            # to invoke main explicitly.
            mod.main()
        except NativeModuleExit, e:
            return e.dct

        return {
            'failed': True,
            'msg': 'ansible_mitogen: module did not exit normally.'
        }


class BinaryRunner(Runner):
    def __init__(self, path, **kwargs):
        super(BinaryRunner, self).__init__(**kwargs)
        self.path = path

    def setup(self):
        super(BinaryRunner, self).setup()
        self._setup_binary()
        self._setup_args()

    def _get_binary(self):
        """
        Fetch the module binary from the master if necessary.
        """
        return ansible_mitogen.helpers.get_file(
            path=self.runner_params['path'],
        )

    def _get_args(self):
        """
        Return the module arguments formatted as JSON.
        """
        return json.dumps(self.args)

    def _setup_program(self):
        """
        Create a temporary file containing the program code. The code is
        fetched via :meth:`_get_binary`.
        """
        self.bin_fp = tempfile.NamedTemporaryFile(
            prefix='ansible_mitogen',
            suffix='-binary',
        )
        self.bin_fp.write(self._get_binary())
        self.bin_fp.flush()
        os.chmod(self.fp.name, int('0700', 8))

    def _setup_args(self):
        """
        Create a temporary file containing the module's arguments. The
        arguments are formatted via :meth:`_get_args`.
        """
        self.args_fp = tempfile.NamedTemporaryFile(
            prefix='ansible_mitogen',
            suffix='-args',
        )
        self.args_fp.write(self._get_args())
        self.args_fp.flush()

    def revert(self):
        """
        Delete the temporary binary and argument files.
        """
        self.args_fp.close()
        self.bin_fp.close()
        super(BinaryRunner, self).revert()

    def _run(self):
        try:
            rc, stdout, stderr = ansible_mitogen.helpers.exec_args(
                args=[self.bin_fp.name, self.args_fp.name],
            )
        except Exception, e:
            return {
                'failed': True,
                'msg': '%s: %s' % (type(e), e),
            }

        return {
            'rc': rc,
            'stdout': stdout,
            'stderr': stderr
        }


class WantJsonRunner(BinaryRunner):
    def _get_binary(self):
        s = super(WantJsonRunner, self)._get_binary()
        # fix up shebang.
        return s


class OldStyleRunner(BinaryRunner):
    def _get_args(self):
        """
        Mimic the argument formatting behaviour of
        ActionBase._execute_module().
        """
        return ' '.join(
            '%s=%s' % (key, shlex_quote(str(self.args[key])))
            for key in self.args
        )
