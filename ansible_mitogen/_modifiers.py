# SPDX-FileCopyrightText: 2026 Mitogen authors <https://github.com/mitogen-hq>
# SPDX-License-Identifier: BSD-3-Clause
# !mitogen: minify_safe

from __future__ import absolute_import, division, print_function

import inspect
import logging
import re

import ansible_mitogen.utils

LOG = logging.getLogger(__name__)

class ReplaceCountError(ValueError):
    pass


class _DummyDnfModule:
    """
    Placeholder containing methods to be injected into Ansible's DNF module.
    """
    def _execute_dnf_script(self, command, config, params=None):
        """
        Run ansible.module_utils._embed.dnf.* using a Mitogen context,
        instead of ansible.module_utils.embed.EmbedManager.
        """
        params = params or {}
        python_executable = self._interpreter or sys.executable

        router = sys.modules['__main__'].ansible_mitogen_injected_router
        context = router.local(python_path=python_executable)

        if command == 'list':
            list_command = params.get('list_command')
            if not list_command:
                return {
                    'failed': True,
                    'msg': 'No list_command specified for list operation',
                }
            return context.call(_embed_dnf.list_items, list_command)

        if command == 'ensure':
            return context.call(_embed_dnf.ensure, config, params)

        if command == 'update-cache':
            return context.call(_embed_dnf.update_cache_only, config)

        return {'failed': True, 'msg': 'Unknown command: %s' % (command,)}


def _replace_exactly_n(string, old, new, count):
    """
    Return a copy of string with count occurences of old replaced by new.

    If fewer than count replacements are made, raise ReplaceCountError.
    """
    if count < 0:
        raise ValueError("Count must be >= 0, got %d" % count)
    if count == 0:
        return string

    # Pass repl arg as a callback to bypass backref/backslash processing
    pattern = re.compile(re.escape(old))
    string, subs_count = pattern.subn(lambda match: new, string, count=count)
    if subs_count < count:
        raise ReplaceCountError(
            "Expected %d replacements, performed %d" % (count, subs_count),
        )
    return string


def ansiblemodule_abs_import(fullname, path, source, is_pkg):
    """
    Ansible's setup module fails under Mitogen, on Python 3.5.1-3.5.3 due to a
    relative import.

    https://github.com/mitogen-hq/mitogen/issues/672#issuecomment-636408833
    """
    source = _replace_exactly_n(
        source,
        b"from ..module_utils.basic import AnsibleModule",
        b"from ansible.module_utils.basic import AnsibleModule",
        1,
    )
    return (path, source, is_pkg)


def dnf_cli_import(fullname, path, source, is_pkg):
    """
    Some DNF plugins use dnf.cli without importing it. Warnings sometimes
    appear on stderr (e.g. "Failed loading plugin 'debuginfo-install': module
    'dnf' has no attribute 'cli'"). Importing 'dnf.cli' early avoids this.

    https://github.com/mitogen-hq/mitogen/issues/1143
    """
    source = _replace_exactly_n(
        source,
        b"import dnf\n",
        b"import dnf, dnf.cli\n",
        1,
    )
    return (path, source, is_pkg)


def dnfmodule_no_embedmanager(fullname, path, source, is_pkg):
    """
    Ansible 14 (ansible-core 2.21) adds ansible.module_utils.embed.EmbedManager,
    as a tech preview to embed files in ansiballz. The DNF module uses it to
    embed ansible.module_utils._embed.dnf and runs `{python} -m ..._embed.dnf`
    on the target. See https://github.com/ansible/ansible/pull/86432.

    Mitogen has no ansiballz, so we replace Ansible's implementation of
    ansible.modules.dnf.DnfModule._execute_dnf_script() with one that calls
    ansible.module_utils._embed.dnf.ensure() et al through a Mitogen context.
    """
    source = _replace_exactly_n(
        source,
        b'from ansible.module_utils.embed import EmbedManager\n',
        b'',
        1,
    )
    source = _replace_exactly_n(
        source,
        b"dnfscript = EmbedManager.embed('..module_utils._embed', 'dnf.py')\n",
        b'from ansible.module_utils._embed import dnf as _embed_dnf\n',
        1,
    )
    source = _replace_exactly_n(
        source,
        b'    def _execute_dnf_script(self, command, config, params=None):\n',
        inspect.getsource(_DummyDnfModule._execute_dnf_script).encode('ascii'),
        1,
    )
    return (path, source, is_pkg)


_ANSIBLE_MODULE_MODIFIERS = {
    'ansible.builtin.setup': [ansiblemodule_abs_import],
    'ansible.legacy.setup': [ansiblemodule_abs_import],
    'setup': [ansiblemodule_abs_import],
}

_PYTHON_MODULE_MODIFIERS = {
    'ansible.modules.setup': [ansiblemodule_abs_import],
}

if ansible_mitogen.utils.ansible_version[:2] <= (2, 20):
    _ANSIBLE_MODULE_MODIFIERS.update({
        'ansible.builtin.dnf': [dnf_cli_import],
        'ansible.legacy.dnf': [dnf_cli_import],
        'dnf': [dnf_cli_import],
    })
    _PYTHON_MODULE_MODIFIERS.update({
        'ansible.modules.dnf': [dnf_cli_import],
    })
else:
    _ANSIBLE_MODULE_MODIFIERS.update({
        'ansible.builtin.dnf': [dnfmodule_no_embedmanager],
        'ansible.legacy.dnf': [dnfmodule_no_embedmanager],
        'dnf': [dnfmodule_no_embedmanager],
    })
    _PYTHON_MODULE_MODIFIERS.update({
        'ansible.module_utils._embed.dnf': [dnf_cli_import],
        'ansible.modules.dnf': [dnfmodule_no_embedmanager],
    })


def apply_ansible_module_modifiers(name, source):
    for callable in _ANSIBLE_MODULE_MODIFIERS.get(name, []):
        _, source, _ = callable('IGNORED', 'IGNORED', source, False)
    return source


def register_moduleresponder_modifiers(responder):
    for fullname, callables in _PYTHON_MODULE_MODIFIERS.items():
        for callable in callables:
            responder.add_source_modifier(fullname, callable)
