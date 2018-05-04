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
Helper functions intended to be executed on the target. These are entrypoints
for file transfer, module execution and sundry bits like changing file modes.
"""

from __future__ import absolute_import
import cStringIO
import errno
import grp
import json
import logging
import operator
import os
import pwd
import random
import re
import stat
import subprocess
import tempfile
import time
import traceback

import ansible.module_utils.json_utils
import ansible_mitogen.runner
import ansible_mitogen.services
import mitogen.core
import mitogen.fork
import mitogen.parent
import mitogen.service


LOG = logging.getLogger(__name__)

#: Set by init_child() to the single temporary directory that will exist for
#: the duration of the process.
temp_dir = None

#: Caching of fetched file data.
_file_cache = {}

#: Initialized to an econtext.parent.Context pointing at a pristine fork of
#: the target Python interpreter before it executes any code or imports.
_fork_parent = None


def _get_file(context, path, out_fp):
    """
    Streamily download a file from the connection multiplexer process in the
    controller.

    :param mitogen.core.Context context:
        Reference to the context hosting the FileService that will be used to
        fetch the file.
    :param bytes in_path:
        FileService registered name of the input file.
    :param bytes out_path:
        Name of the output path on the local disk.
    :returns:
        :data:`True` on success, or :data:`False` if the transfer was
        interrupted and the output should be discarded.
    """
    LOG.debug('_get_file(): fetching %r from %r', path, context)
    t0 = time.time()
    recv = mitogen.core.Receiver(router=context.router)
    metadata = mitogen.service.call(
        context=context,
        handle=ansible_mitogen.services.FileService.handle,
        method='fetch',
        kwargs={
            'path': path,
            'sender': recv.to_sender()
        }
    )

    for chunk in recv:
        s = chunk.unpickle()
        LOG.debug('_get_file(%r): received %d bytes', path, len(s))
        mitogen.service.call_async(
            context=context,
            handle=ansible_mitogen.services.FileService.handle,
            method='acknowledge',
            kwargs={
                'size': len(s),
            }
        ).close()
        out_fp.write(s)

    ok = out_fp.tell() == metadata['size']
    if not ok:
        LOG.error('get_file(%r): receiver was closed early, controller '
                  'is likely shutting down.', path)

    LOG.debug('target.get_file(): fetched %d bytes of %r from %r in %dms',
              metadata['size'], path, context, 1000 * (time.time() - t0))
    return ok, metadata


def get_file(context, path):
    """
    Basic in-memory caching module fetcher. This generates an one roundtrip for
    every previously unseen file, so it is only a temporary solution.

    :param context:
        Context we should direct FileService requests to. For now (and probably
        forever) this is just the top-level Mitogen connection manager process.
    :param path:
        Path to fetch from FileService, must previously have been registered by
        a privileged context using the `register` command.
    :returns:
        Bytestring file data.
    """
    if path not in _file_cache:
        io = cStringIO.StringIO()
        ok, metadata = _get_file(context, path, io)
        if not ok:
            raise IOError('transfer of %r was interrupted.' % (path,))
        _file_cache[path] = io.getvalue()
    return _file_cache[path]


def transfer_file(context, in_path, out_path, sync=False, set_owner=False):
    """
    Streamily download a file from the connection multiplexer process in the
    controller.

    :param mitogen.core.Context context:
        Reference to the context hosting the FileService that will be used to
        fetch the file.
    :param bytes in_path:
        FileService registered name of the input file.
    :param bytes out_path:
        Name of the output path on the local disk.
    :param bool sync:
        If :data:`True`, ensure the file content and metadat are fully on disk
        before renaming the temporary file over the existing file. This should
        ensure in the case of system crash, either the entire old or new file
        are visible post-reboot.
    :param bool set_owner:
        If :data:`True`, look up the metadata username and group on the local
        system and file the file owner using :func:`os.fchmod`.
    """
    out_path = os.path.abspath(out_path)
    fd, tmp_path = tempfile.mkstemp(suffix='.tmp',
                                    prefix='.ansible_mitogen_transfer-',
                                    dir=os.path.dirname(out_path))
    fp = os.fdopen(fd, 'wb', mitogen.core.CHUNK_SIZE)
    LOG.debug('transfer_file(%r) temporary file: %s', out_path, tmp_path)

    try:
        try:
            ok, metadata = _get_file(context, in_path, fp)
            if not ok:
                raise IOError('transfer of %r was interrupted.' % (in_path,))

            os.fchmod(fp.fileno(), metadata['mode'])
            if set_owner:
                set_fd_owner(fp.fileno(), metadata['owner'], metadata['group'])
        finally:
            fp.close()

        if sync:
            os.fsync(fp.fileno())
        os.rename(tmp_path, out_path)
    except BaseException:
        os.unlink(tmp_path)
        raise

    os.utime(out_path, (metadata['atime'], metadata['mtime']))


def prune_tree(path):
    """
    Like shutil.rmtree(), but log errors rather than discard them, and do not
    waste multiple os.stat() calls discovering whether the object can be
    deleted, just try deleting it instead.
    """
    try:
        os.unlink(path)
        return
    except OSError, e:
        if not (os.path.isdir(path) and
                e.args[0] in (errno.EPERM, errno.EISDIR)):
            LOG.error('prune_tree(%r): %s', path, e)
            return

    try:
        # Ensure write access for readonly directories. Ignore error in case
        # path is on a weird filesystem (e.g. vfat).
        os.chmod(path, int('0700', 8))
    except OSError, e:
        LOG.warning('prune_tree(%r): %s', path, e)

    try:
        for name in os.listdir(path):
            if name not in ('.', '..'):
                prune_tree(os.path.join(path, name))
        os.rmdir(path)
    except OSError, e:
        LOG.error('prune_tree(%r): %s', path, e)


def _on_broker_shutdown():
    """
    Respond to broker shutdown (graceful termination by parent, or loss of
    connection to parent) by deleting our sole temporary directory.
    """
    prune_tree(temp_dir)


def reset_temp_dir(econtext):
    """
    Create one temporary directory to be reused by all runner.py invocations
    for the lifetime of the process. The temporary directory is changed for
    each forked job, and emptied as necessary by runner.py::_cleanup_temp()
    after each module invocation.

    The result is that a context need only create and delete one directory
    during startup and shutdown, and no further filesystem writes need occur
    assuming no modules execute that create temporary files.
    """
    global temp_dir
    # https://github.com/dw/mitogen/issues/239
    temp_dir = tempfile.mkdtemp(prefix='ansible_mitogen_')

    # This must be reinstalled in forked children too, since the Broker
    # instance from the parent process does not carry over to the new child.
    mitogen.core.listen(econtext.broker, 'shutdown', _on_broker_shutdown)


@mitogen.core.takes_econtext
def init_child(econtext):
    """
    Called by ContextService immediately after connection; arranges for the
    (presently) spotless Python interpreter to be forked, where the newly
    forked interpreter becomes the parent of any newly forked future
    interpreters.

    This is necessary to prevent modules that are executed in-process from
    polluting the global interpreter state in a way that effects explicitly
    isolated modules.
    """
    global _fork_parent
    mitogen.parent.upgrade_router(econtext)
    _fork_parent = econtext.router.fork()
    reset_temp_dir(econtext)


@mitogen.core.takes_econtext
def start_fork_child(wrap_async, kwargs, econtext):
    mitogen.parent.upgrade_router(econtext)
    context = econtext.router.fork()
    if not wrap_async:
        try:
            return context.call(run_module, kwargs)
        finally:
            context.shutdown()

    job_id = '%016x' % random.randint(0, 2**64)
    context.call_async(run_module_async, job_id, kwargs)
    return {
        'stdout': json.dumps({
            # modules/utilities/logic/async_wrapper.py::_run_module().
            'changed': True,
            'started': 1,
            'finished': 0,
            'ansible_job_id': job_id,
        })
    }


@mitogen.core.takes_econtext
def run_module(kwargs, econtext):
    """
    Set up the process environment in preparation for running an Ansible
    module. This monkey-patches the Ansible libraries in various places to
    prevent it from trying to kill the process on completion, and to prevent it
    from reading sys.stdin.
    """
    should_fork = kwargs.pop('should_fork', False)
    wrap_async = kwargs.pop('wrap_async', False)
    if should_fork:
        return _fork_parent.call(start_fork_child, wrap_async, kwargs)

    runner_name = kwargs.pop('runner_name')
    klass = getattr(ansible_mitogen.runner, runner_name)
    impl = klass(**kwargs)
    return impl.run()


def _get_async_dir():
    return os.path.expanduser(
        os.environ.get('ANSIBLE_ASYNC_DIR', '~/.ansible_async')
    )


def _write_job_status(job_id, dct):
    """
    Update an async job status file.
    """
    LOG.info('_write_job_status(%r, %r)', job_id, dct)
    dct.setdefault('ansible_job_id', job_id)
    dct.setdefault('data', '')

    async_dir = _get_async_dir()
    if not os.path.exists(async_dir):
        os.makedirs(async_dir)

    path = os.path.join(async_dir, job_id)
    with open(path + '.tmp', 'w') as fp:
        fp.write(json.dumps(dct))
    os.rename(path + '.tmp', path)


def _run_module_async(job_id, kwargs, econtext):
    """
    Body on run_module_async().

    1. Immediately updates the status file to mark the job as started.
    2. Installs a timer/signal handler to implement the time limit.
    3. Runs as with run_module(), writing the result to the status file.
    """
    _write_job_status(job_id, {
        'started': 1,
        'finished': 0
    })

    kwargs['emulate_tty'] = False
    dct = run_module(kwargs, econtext)
    if mitogen.core.PY3:
        for key in 'stdout', 'stderr':
            dct[key] = dct[key].decode('utf-8', 'surrogateescape')

    try:
        filtered, warnings = (
            ansible.module_utils.json_utils.
            _filter_non_json_lines(dct['stdout'])
        )
        result = json.loads(filtered)
        result.setdefault('warnings', []).extend(warnings)
        result['stderr'] = dct['stderr']
        _write_job_status(job_id, result)
    except Exception:
        _write_job_status(job_id, {
            "failed": 1,
            "msg": traceback.format_exc(),
            "data": dct['stdout'],  # temporary notice only
            "stderr": dct['stderr']
        })


@mitogen.core.takes_econtext
def run_module_async(job_id, kwargs, econtext):
    """
    Since run_module_async() is invoked with .call_async(), with nothing to
    read the result from the corresponding Receiver, wrap the body in an
    exception logger, and wrap that in something that tears down the context on
    completion.
    """
    try:
        try:
            reset_temp_dir(econtext)
            _run_module_async(job_id, kwargs, econtext)
        except Exception:
            LOG.exception('_run_module_async crashed')
    finally:
        econtext.broker.shutdown()


def make_temp_directory(base_dir):
    """
    Handle creation of `base_dir` if it is absent, in addition to a unique
    temporary directory within `base_dir`. This is the temporary directory that
    becomes 'remote_tmp', not the one used by Ansiballz. It always uses the
    system temporary directory.

    :returns:
        Newly created temporary directory.
    """
    if not os.path.exists(base_dir):
        os.makedirs(base_dir, mode=int('0700', 8))
    return tempfile.mkdtemp(
        dir=base_dir,
        prefix='ansible-mitogen-tmp-',
    )


def get_user_shell():
    """
    For commands executed directly via an SSH command-line, SSH looks up the
    user's shell via getpwuid() and only defaults to /bin/sh if that field is
    missing or empty.
    """
    try:
        pw_shell = pwd.getpwuid(os.geteuid()).pw_shell
    except KeyError:
        pw_shell = None

    return pw_shell or '/bin/sh'


def exec_args(args, in_data='', chdir=None, shell=None, emulate_tty=False):
    """
    Run a command in a subprocess, emulating the argument handling behaviour of
    SSH.

    :param list[str]:
        Argument vector.
    :param bytes in_data:
        Optional standard input for the command.
    :param bool emulate_tty:
        If :data:`True`, arrange for stdout and stderr to be merged into the
        stdout pipe and for LF to be translated into CRLF, emulating the
        behaviour of a TTY.
    :return:
        (return code, stdout bytes, stderr bytes)
    """
    LOG.debug('exec_args(%r, ..., chdir=%r)', args, chdir)
    assert isinstance(args, list)

    if emulate_tty:
        stderr = subprocess.STDOUT
    else:
        stderr = subprocess.PIPE

    proc = subprocess.Popen(
        args=args,
        stdout=subprocess.PIPE,
        stderr=stderr,
        stdin=subprocess.PIPE,
        cwd=chdir,
    )
    stdout, stderr = proc.communicate(in_data)

    if emulate_tty:
        stdout = stdout.replace('\n', '\r\n')
    return proc.returncode, stdout, stderr or ''


def exec_command(cmd, in_data='', chdir=None, shell=None, emulate_tty=False):
    """
    Run a command in a subprocess, emulating the argument handling behaviour of
    SSH.

    :param bytes cmd:
        String command line, passed to user's shell.
    :param bytes in_data:
        Optional standard input for the command.
    :return:
        (return code, stdout bytes, stderr bytes)
    """
    assert isinstance(cmd, basestring)
    return exec_args(
        args=[get_user_shell(), '-c', cmd],
        in_data=in_data,
        chdir=chdir,
        shell=shell,
        emulate_tty=emulate_tty,
    )


def read_path(path):
    """
    Fetch the contents of a filesystem `path` as bytes.
    """
    return open(path, 'rb').read()


def set_fd_owner(fd, owner, group=None):
    if owner:
        uid = pwd.getpwnam(owner).pw_uid
    else:
        uid = os.geteuid()

    if group:
        gid = grp.getgrnam(group).gr_gid
    else:
        gid = os.getegid()

    os.fchown(fd, (uid, gid))


def write_path(path, s, owner=None, group=None, mode=None,
               utimes=None, sync=False):
    """
    Writes bytes `s` to a filesystem `path`.
    """
    path = os.path.abspath(path)
    fd, tmp_path = tempfile.mkstemp(suffix='.tmp',
                                    prefix='.ansible_mitogen_transfer-',
                                    dir=os.path.dirname(path))
    fp = os.fdopen(fd, 'wb', mitogen.core.CHUNK_SIZE)
    LOG.debug('write_path(path=%r) tempory file: %s', path, tmp_path)

    try:
        try:
            if mode:
                os.fchmod(fp.fileno(), mode)
            if owner or group:
                set_fd_owner(fp.fileno(), owner, group)
            fp.write(s)
        finally:
            fp.close()

        if sync:
            os.fsync(fp.fileno())
        os.rename(tmp_path, path)
    except BaseException:
        os.unlink(tmp_path)
        raise

    if utimes:
        os.utime(path, utimes)


CHMOD_CLAUSE_PAT = re.compile(r'([uoga]*)([+\-=])([ugo]|[rwx]*)')
CHMOD_MASKS = {
    'u': stat.S_IRWXU,
    'g': stat.S_IRWXG,
    'o': stat.S_IRWXO,
    'a': (stat.S_IRWXU | stat.S_IRWXG | stat.S_IRWXO),
}
CHMOD_BITS = {
    'u': {'r': stat.S_IRUSR, 'w': stat.S_IWUSR, 'x': stat.S_IXUSR},
    'g': {'r': stat.S_IRGRP, 'w': stat.S_IWGRP, 'x': stat.S_IXGRP},
    'o': {'r': stat.S_IROTH, 'w': stat.S_IWOTH, 'x': stat.S_IXOTH},
    'a': {
        'r': (stat.S_IRUSR | stat.S_IRGRP | stat.S_IROTH),
        'w': (stat.S_IWUSR | stat.S_IWGRP | stat.S_IWOTH),
        'x': (stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    }
}


def apply_mode_spec(spec, mode):
    """
    Given a symbolic file mode change specification in the style of chmod(1)
    `spec`, apply changes in the specification to the numeric file mode `mode`.
    """
    for clause in spec.split(','):
        match = CHMOD_CLAUSE_PAT.match(clause)
        who, op, perms = match.groups()
        for ch in who or 'a':
            mask = CHMOD_MASKS[ch]
            bits = CHMOD_BITS[ch]
            cur_perm_bits = mode & mask
            new_perm_bits = reduce(operator.or_, (bits[p] for p in perms), 0)
            mode &= ~mask
            if op == '=':
                mode |= new_perm_bits
            elif op == '+':
                mode |= new_perm_bits | cur_perm_bits
            else:
                mode |= cur_perm_bits & ~new_perm_bits
    return mode


def set_file_mode(path, spec):
    """
    Update the permissions of a file using the same syntax as chmod(1).
    """
    mode = os.stat(path).st_mode

    if spec.isdigit():
        new_mode = int(spec, 8)
    else:
        new_mode = apply_mode_spec(spec, mode)

    os.chmod(path, new_mode)
