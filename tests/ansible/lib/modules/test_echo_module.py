#!/usr/bin/python
# -*- coding: utf-8 -*-

# (c) 2012, Michael DeHaan <michael.dehaan@gmail.com>
# (c) 2016, Toshio Kuratomi <tkuratomi@ansible.com>
# (c) 2020, Steven Robertson <srtrumpetaggie@gmail.com>
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)

from __future__ import absolute_import, division, print_function
__metaclass__ = type

import os
import stat
import platform
import subprocess
import sys

from ansible.module_utils.basic import AnsibleModule


# trace_realpath() and _join_tracepath() adapated from stdlib posixpath.py
# https://github.com/python/cpython/blob/v3.12.6/Lib/posixpath.py#L423-L492
# Copyright (c) 2001 - 2023 Python Software Foundation
# Copyright (c) 2024 Alex Willmer <alex@moreati.org.uk>
# License: Python Software Foundation License Version 2

def trace_realpath(filename, strict=False):
    """
    Return the canonical path of the specified filename, and a trace of
    the route taken, eliminating any symbolic links encountered in the path.
    """
    path, trace, ok = _join_tracepath(filename[:0], filename, strict, seen={}, trace=[])
    return os.path.abspath(path), trace


def _join_tracepath(path, rest, strict, seen, trace):
    """
    Join two paths, normalizing and eliminating any symbolic links encountered
    in the second path.
    """
    trace.append(rest)
    if isinstance(path, bytes):
        sep = b'/'
        curdir = b'.'
        pardir = b'..'
    else:
        sep = '/'
        curdir = '.'
        pardir = '..'

    if os.path.isabs(rest):
        rest = rest[1:]
        path = sep

    while rest:
        name, _, rest = rest.partition(sep)
        if not name or name == curdir:
            # current dir
            continue
        if name == pardir:
            # parent dir
            if path:
                path, name = os.path.split(path)
                if name == pardir:
                    path = os.path.join(path, pardir, pardir)
            else:
                path = pardir
            continue
        newpath = os.path.join(path, name)
        try:
            st = os.lstat(newpath)
        except OSError:
            if strict:
                raise
            is_link = False
        else:
            is_link = stat.S_ISLNK(st.st_mode)
        if not is_link:
            path = newpath
            continue
        # Resolve the symbolic link
        if newpath in seen:
            # Already seen this path
            path = seen[newpath]
            if path is not None:
                # use cached value
                continue
            # The symlink is not resolved, so we must have a symlink loop.
            if strict:
                # Raise OSError(errno.ELOOP)
                os.stat(newpath)
            else:
                # Return already resolved part + rest of the path unchanged.
                return os.path.join(newpath, rest), trace, False
        seen[newpath] = None # not resolved symlink
        path, trace, ok = _join_tracepath(path, os.readlink(newpath), strict, seen, trace)
        if not ok:
            return os.path.join(path, rest), False
        seen[newpath] = path # resolved symlink

    return path, trace, True


def main():
    module = AnsibleModule(argument_spec=dict(
        facts_copy=dict(type=dict, default={}),
        facts_to_override=dict(type=dict, default={})
    ))

    # revert the Mitogen OSX tweak since discover_interpreter() doesn't return this info
    # NB This must be synced with mitogen.parent.Connection.get_boot_command()
    platform_release_major = int(platform.release().partition('.')[0])
    if sys.modules.get('mitogen') and sys.platform == 'darwin':
        if platform_release_major < 19 and sys.executable == '/usr/bin/python2.7':
            sys.executable = '/usr/bin/python'
        if platform_release_major in (20, 21) and sys.version_info[:2] == (2, 7):
            # only for tests to check version of running interpreter -- Mac 10.15+ changed python2
            # so it looks like it's /usr/bin/python but actually it's /System/Library/Frameworks/Python.framework/Versions/2.7/Resources/Python.app/Contents/MacOS/Python
            sys.executable = "/usr/bin/python"

    facts_copy = module.params['facts_copy']

    discovered_interpreter_python = facts_copy['discovered_interpreter_python']
    d_i_p_realpath, d_i_p_trace = trace_realpath(discovered_interpreter_python)
    d_i_p_proc = subprocess.Popen(
        [discovered_interpreter_python, '-c', 'import sys; print(sys.executable)'],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,

    )
    d_i_p_stdout, d_i_p_stderr = d_i_p_proc.communicate()

    sys_exec_realpath, sys_exec_trace = trace_realpath(sys.executable)

    result = {
        'changed': False,
        'ansible_facts': module.params['facts_to_override'],
        'discovered_and_running_samefile': os.path.samefile(
            os.path.realpath(discovered_interpreter_python),
            os.path.realpath(sys.executable),
        ),
        'discovered_python': {
            'as_seen': discovered_interpreter_python,
            'resolved': d_i_p_realpath,
            'trace': [os.path.abspath(p) for p in  d_i_p_trace],
            'sys': {
                'executable': {
                    'as_seen': d_i_p_stdout.decode('ascii').rstrip('\n'),
                    'proc': {
                        'stderr': d_i_p_stderr.decode('ascii'),
                        'returncode': d_i_p_proc.returncode,
                    },
                },
            },
        },
        'running_python': {
            'platform': {
                'release': {
                    'major': platform_release_major,
                },
            },
            'sys': {
                'executable': {
                    'as_seen': sys.executable,
                    'resolved': sys_exec_realpath,
                    'trace': [os.path.abspath(p) for p in sys_exec_trace],
                },
                'platform': sys.platform,
                'version_info': {
                    'major': sys.version_info[0],
                    'minor': sys.version_info[1],
                },
            },
        },
    }

    module.exit_json(**result)


if __name__ == '__main__':
    main()