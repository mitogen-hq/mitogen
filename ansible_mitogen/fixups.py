# SPDX-FileCopyrightText: 2026 Mitogen authors <https://github.com/mitogen-hq>
# SPDX-License-Identifier: BSD-3-Clause
# !mitogen: minify_safe

from __future__ import absolute_import, division, print_function

import abc
import inspect

import ansible_mitogen.utils


class Fixup(object):
    @abc.abstractmethod
    def matches(self, plugin_type, name): raise NotImplemented

    @abc.abstractmethod
    def apply(self, source): raise NotImplemented


class AnsibleModuleImportFixup(Fixup):
    """
    Ansible's setup module fails under Mitogen, on Python 3.5.1-3.5.3 due to a
    relative import.
    https://github.com/mitogen-hq/mitogen/issues/672#issuecomment-636408833
    """
    def matches(self, plugin_type, name):
        return (
            plugin_type == 'modules'
            and name in {'setup', 'ansible.builtin.setup', 'ansible.legacy.setup'}
        )

    def apply(self, source):
        return source.replace(
            b"from ..module_utils.basic import AnsibleModule",
            b"from ansible.module_utils.basic import AnsibleModule",
            1,
        )


class DNFCLIFixup(Fixup):
    """
    Ansible's dnf module emits errors/warning under Mitogen (e.g. "Failed
    loading plugin 'debuginfo-install': module 'dnf' has no attribute 'cli'")
    Explicitly importing 'dnf.cli' prevents this.
    https://github.com/mitogen-hq/mitogen/issues/1143
    """
    def matches(self, plugin_type, name):
        return (
            plugin_type == 'modules'
            and name in {'dnf', 'ansible.builtin.dnf', 'ansible.legacy.dnf'}
        )

    def apply(self, source):
        return source.replace(
            b"import dnf\n",
            b"import dnf, dnf.cli\n",
            1,
        )


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


class DNFEmbeddedFixup(Fixup):
    """
    Ansible 14 (ansible-core 2.21) adds ansible.module_utils.embed.EmbedManager,
    as a tech preview to embed files in ansiballz. The DNF module uses it to
    embed ansible.module_utils._embed.dnf and runs `{python} -m ..._embed.dnf`
    on the target. See https://github.com/ansible/ansible/pull/86432.

    Mitogen has no ansiballz, so we replace Ansible's implementation of
    ansible.modules.dnf.DnfModule._execute_dnf_script() with one that calls
    ansible.module_utils._embed.dnf.ensure() et al through a Mitogen context.
    """
    def matches(self, plugin_type, name):
        return (
            ansible_mitogen.utils.ansible_version[:2] == (2, 21)
            and plugin_type == 'modules'
            and name in {'dnf', 'ansible.builtin.dnf', 'ansible.legacy.dnf'}
        )

    def apply(self, source):
        source = source.replace(
            b'from ansible.module_utils.embed import EmbedManager\n',
            b'',
            1,
        )
        source = source.replace(
            b"dnfscript = EmbedManager.embed('..module_utils._embed', 'dnf.py')\n",
            b'from ansible.module_utils._embed import dnf as _embed_dnf\n',
            1,
        )
        source = source.replace(
            b'    def _execute_dnf_script(self, command, config, params=None):\n',
            inspect.getsource(_DummyDnfModule._execute_dnf_script).encode('ascii'),
            1,
        )
        return source


_FIXUPS = {
    'modules': {
        'setup': [AnsibleModuleImportFixup],
        'ansible.builtin.setup': [AnsibleModuleImportFixup],
        'ansible.legacy.setup': [AnsibleModuleImportFixup],
        'dnf': [DNFCLIFixup, DNFEmbeddedFixup],
        'ansible.builtin.dnf': [DNFCLIFixup, DNFEmbeddedFixup],
        'ansible.legacy.dnf': [DNFCLIFixup, DNFEmbeddedFixup],
    },
}


def _apply(plugin_type, name, source):
    try:
        fixup_classes = _FIXUPS[plugin_type][name]
    except KeyError:
        return source

    for fixup_class in fixup_classes:
        fixup = fixup_class()
        if not fixup.matches(plugin_type, name): continue
        source = fixup.apply(source)

    return source
