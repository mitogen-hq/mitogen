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
instantiated in the target context by way of target.py::run_module().

Each class in here has a corresponding Planner class in planners.py that knows
how to build arguments for it, preseed related data, etc.
"""

from __future__ import absolute_import
from __future__ import unicode_literals

import ctypes
import errno
import imp
import json
import logging
import os
import sys
import tempfile
import types

import mitogen.core
import ansible_mitogen.target  # TODO: circular import

try:
    # Cannot use cStringIO as it does not support Unicode.
    from StringIO import StringIO
except ImportError:
    from io import StringIO

try:
    from shlex import quote as shlex_quote
except ImportError:
    from pipes import quote as shlex_quote

# Prevent accidental import of an Ansible module from hanging on stdin read.
import ansible.module_utils.basic
ansible.module_utils.basic._ANSIBLE_ARGS = '{}'

# For tasks that modify /etc/resolv.conf, non-Debian derivative glibcs cache
# resolv.conf at startup and never implicitly reload it. Cope with that via an
# explicit call to res_init() on each task invocation. BSD-alikes export it
# directly, Linux #defines it as "__res_init".
libc = ctypes.CDLL(None)
libc__res_init = None
for symbol in 'res_init', '__res_init':
    try:
        libc__res_init = getattr(libc, symbol)
    except AttributeError:
        pass

iteritems = getattr(dict, 'iteritems', dict.items)
LOG = logging.getLogger(__name__)


def utf8(s):
    """
    Coerce an object to bytes if it is Unicode.
    """
    if isinstance(s, mitogen.core.UnicodeType):
        s = s.encode('utf-8')
    return s


def reopen_readonly(fp):
    """
    Replace the file descriptor belonging to the file object `fp` with one
    open on the same file (`fp.name`), but opened with :py:data:`os.O_RDONLY`.
    This enables temporary files to be executed on Linux, which usually throws
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

    :param str module:
        Name of the module to execute, e.g. "shell"
    :param mitogen.core.Context service_context:
        Context to which we should direct FileService calls. For now, always
        the connection multiplexer process on the controller.
    :param str json_args:
        Ansible module arguments. A mixture of user and internal keys created
        by :meth:`ansible.plugins.action.ActionBase._execute_module`.

        This is passed as a string rather than a dict in order to mimic the
        implicit bytes/str conversion behaviour of a 2.x controller running
        against a 3.x target.
    :param dict env:
        Additional environment variables to set during the run. Keys with
        :data:`None` are unset if present.
    :param str cwd:
        If not :data:`None`, change to this directory before executing.
    :param mitogen.core.ExternalContext econtext:
        When `detach` is :data:`True`, a reference to the ExternalContext the
        runner is executing in.
    :param bool detach:
        When :data:`True`, indicate the runner should detach the context from
        its parent after setup has completed successfully.
    """
    def __init__(self, module, service_context, json_args, extra_env=None,
                 cwd=None, env=None, econtext=None, detach=False):
        self.module = module
        self.service_context = service_context
        self.econtext = econtext
        self.detach = detach
        self.args = json.loads(json_args)
        self.extra_env = extra_env
        self.env = env
        self.cwd = cwd

    def setup(self):
        """
        Prepare for running a module, including fetching necessary dependencies
        from the parent, as :meth:`run` may detach prior to beginning
        execution. The base implementation simply prepares the environment.
        """
        if self.cwd:
            # For situations like sudo to another non-privileged account, the
            # CWD could be $HOME of the old account, which could have mode go=,
            # which means it is impossible to restore the old directory, so
            # don't even bother.
            os.chdir(self.cwd)
        env = dict(self.extra_env or {})
        if self.env:
            env.update(self.env)
        self._env = TemporaryEnvironment(env)

    def revert(self):
        """
        Revert any changes made to the process after running a module. The base
        implementation simply restores the original environment.
        """
        self._env.revert()
        self._try_cleanup_temp()

    def _cleanup_temp(self):
        """
        Empty temp_dir in time for the next module invocation.
        """
        for name in os.listdir(ansible_mitogen.target.temp_dir):
            if name in ('.', '..'):
                continue

            path = os.path.join(ansible_mitogen.target.temp_dir, name)
            LOG.debug('Deleting %r', path)
            ansible_mitogen.target.prune_tree(path)

    def _try_cleanup_temp(self):
        """
        During broker shutdown triggered by async task timeout or loss of
        connection to the parent, it is possible for prune_tree() in
        target.py::_on_broker_shutdown() to run before _cleanup_temp(), so skip
        cleanup if the directory or a file disappears from beneath us.
        """
        try:
            self._cleanup_temp()
        except (IOError, OSError) as e:
            if e.args[0] == errno.ENOENT:
                return
            raise

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
        if self.detach:
            self.econtext.detach()

        try:
            return self._run()
        finally:
            self.revert()


class ModuleUtilsImporter(object):
    """
    :param list module_utils:
        List of `(fullname, path, is_pkg)` tuples.
    """
    def __init__(self, context, module_utils):
        self._context = context
        self._by_fullname = dict(
            (fullname, (path, is_pkg))
            for fullname, path, is_pkg in module_utils
        )
        self._loaded = set()
        sys.meta_path.insert(0, self)

    def revert(self):
        sys.meta_path.remove(self)
        for fullname in self._loaded:
            sys.modules.pop(fullname, None)

    def find_module(self, fullname, path=None):
        if fullname in self._by_fullname:
            return self

    def load_module(self, fullname):
        path, is_pkg = self._by_fullname[fullname]
        source = ansible_mitogen.target.get_small_file(self._context, path)
        code = compile(source, path, 'exec', 0, 1)
        mod = sys.modules.setdefault(fullname, imp.new_module(fullname))
        mod.__file__ = "master:%s" % (path,)
        mod.__loader__ = self
        if is_pkg:
            mod.__path__ = []
            mod.__package__ = fullname
        else:
            mod.__package__ = fullname.rpartition('.')[0]
        exec(code, mod.__dict__)
        self._loaded.add(fullname)
        return mod


class TemporaryEnvironment(object):
    """
    Apply environment changes from `env` until :meth:`revert` is called. Values
    in the dict may be :data:`None` to indicate the relevant key should be
    deleted.
    """
    def __init__(self, env=None):
        self.original = dict(os.environ)
        self.env = env or {}
        for key, value in iteritems(self.env):
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = str(value)

    def revert(self):
        if self.env:
            os.environ.clear()
            os.environ.update(self.original)


class TemporaryArgv(object):
    def __init__(self, argv):
        self.original = sys.argv[:]
        sys.argv[:] = map(str, argv)

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
        sys.stdout = StringIO()
        sys.stderr = StringIO()
        encoded = json.dumps({'ANSIBLE_MODULE_ARGS': args})
        ansible.module_utils.basic._ANSIBLE_ARGS = utf8(encoded)
        sys.stdin = StringIO(mitogen.core.to_text(encoded))

    def revert(self):
        sys.stdout = self.original_stdout
        sys.stderr = self.original_stderr
        sys.stdin = self.original_stdin
        ansible.module_utils.basic._ANSIBLE_ARGS = '{}'


class ProgramRunner(Runner):
    """
    Base class for runners that run external programs.

    :param str path:
        Absolute path to the program file on the master, as it can be retrieved
        via :class:`mitogen.service.FileService`.
    :param bool emulate_tty:
        If :data:`True`, execute the program with `stdout` and `stderr` merged
        into a single pipe, emulating Ansible behaviour when an SSH TTY is in
        use.
    """
    def __init__(self, path, emulate_tty=None, **kwargs):
        super(ProgramRunner, self).__init__(**kwargs)
        self.emulate_tty = emulate_tty
        self.path = path

    def setup(self):
        super(ProgramRunner, self).setup()
        self._setup_program()

    def _get_program_filename(self):
        """
        Return the filename used for program on disk. Ansible uses the original
        filename for non-Ansiballz runs, and "ansible_module_+filename for
        Ansiballz runs.
        """
        return os.path.basename(self.path)

    program_fp = None

    def _setup_program(self):
        """
        Create a temporary file containing the program code. The code is
        fetched via :meth:`_get_program`.
        """
        filename = self._get_program_filename()
        path = os.path.join(ansible_mitogen.target.temp_dir, filename)
        self.program_fp = open(path, 'wb')
        self.program_fp.write(self._get_program())
        self.program_fp.flush()
        os.chmod(self.program_fp.name, int('0700', 8))
        reopen_readonly(self.program_fp)

    def _get_program(self):
        """
        Fetch the module binary from the master if necessary.
        """
        return ansible_mitogen.target.get_small_file(
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
        if self.program_fp:
            self.program_fp.close()
        super(ProgramRunner, self).revert()

    def _run(self):
        try:
            rc, stdout, stderr = ansible_mitogen.target.exec_args(
                args=self._get_program_args(),
                emulate_tty=self.emulate_tty,
            )
        except Exception as e:
            LOG.exception('While running %s', self._get_program_args())
            return {
                'rc': 1,
                'stdout': '',
                'stderr': '%s: %s' % (type(e), e),
            }

        return {
            'rc': rc,
            'stdout': mitogen.core.to_text(stdout),
            'stderr': mitogen.core.to_text(stderr),
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
            dir=ansible_mitogen.target.temp_dir,
        )
        self.args_fp.write(utf8(self._get_args_contents()))
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
        self.args_fp.close()
        super(ArgsFileRunner, self).revert()


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

        shebang = b'#!' + utf8(self.interpreter)
        if self.interpreter_arg:
            shebang += b' ' + utf8(self.interpreter_arg)

        new = [shebang]
        if os.path.basename(self.interpreter).startswith('python'):
            new.append(self.b_ENCODING_STRING)

        _, _, rest = s.partition(b'\n')
        new.append(rest)
        return b'\n'.join(new)


class NewStyleRunner(ScriptRunner):
    """
    Execute a new-style Ansible module, where Module Replacer-related tricks
    aren't required.
    """
    #: path => new-style module bytecode.
    _code_by_path = {}

    def __init__(self, module_map, **kwargs):
        super(NewStyleRunner, self).__init__(**kwargs)
        self.module_map = module_map

    def _setup_imports(self):
        """
        Ensure the local importer and PushFileService has everything for the
        Ansible module before setup() completes, but before detach() is called
        in an asynchronous task.

        The master automatically streams modules towards us concurrent to the
        runner invocation, however there is no public API to synchronize on the
        completion of those preloads. Instead simply reuse the importer's
        synchronization mechanism by importing everything the module will need
        prior to detaching.
        """
        for fullname, _, _ in self.module_map['custom']:
            mitogen.core.import_module(fullname)
        for fullname in self.module_map['builtin']:
            mitogen.core.import_module(fullname)

    def setup(self):
        super(NewStyleRunner, self).setup()

        self._stdio = NewStyleStdio(self.args)
        # It is possible that not supplying the script filename will break some
        # module, but this has never been a bug report. Instead act like an
        # interpreter that had its script piped on stdin.
        self._argv = TemporaryArgv([''])
        self._importer = ModuleUtilsImporter(
            context=self.service_context,
            module_utils=self.module_map['custom'],
        )
        self._setup_imports()
        if libc__res_init:
            libc__res_init()

    def revert(self):
        self._argv.revert()
        self._stdio.revert()
        super(NewStyleRunner, self).revert()

    def _get_program_filename(self):
        """
        See ProgramRunner._get_program_filename().
        """
        return 'ansible_module_' + os.path.basename(self.path)

    def _setup_args(self):
        pass

    def _setup_program(self):
        self.source = ansible_mitogen.target.get_small_file(
            context=self.service_context,
            path=self.path,
        )

    def _get_code(self):
        try:
            return self._code_by_path[self.path]
        except KeyError:
            return self._code_by_path.setdefault(self.path, compile(
                source=self.source,
                filename="master:" + self.path,
                mode='exec',
                dont_inherit=True,
            ))

    if mitogen.core.PY3:
        main_module_name = '__main__'
    else:
        main_module_name = b'__main__'

    def _run(self):
        code = self._get_code()

        mod = types.ModuleType(self.main_module_name)
        mod.__package__ = None
        # Some Ansible modules use __file__ to find the Ansiballz temporary
        # directory. We must provide some temporary path in __file__, but we
        # don't want to pointlessly write the module to disk when it never
        # actually needs to exist. So just pass the filename as it would exist.
        mod.__file__ = os.path.join(
            ansible_mitogen.target.temp_dir,
            'ansible_module_' + os.path.basename(self.path),
        )

        exc = None
        try:
            if mitogen.core.PY3:
                exec(code, vars(mod))
            else:
                exec('exec code in vars(mod)')
        except SystemExit as e:
            exc = e

        return {
            'rc': exc.args[0] if exc else 2,
            'stdout': mitogen.core.to_text(sys.stdout.getvalue()),
            'stderr': mitogen.core.to_text(sys.stderr.getvalue()),
        }


class JsonArgsRunner(ScriptRunner):
    JSON_ARGS = b'<<INCLUDE_ANSIBLE_MODULE_JSON_ARGS>>'

    def _get_args_contents(self):
        return json.dumps(self.args).encode()

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
