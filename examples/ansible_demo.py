"""
Minimal demo of running an Ansible module via econtext.
"""

import json
import logging
import time

import econtext
import econtext.master
import econtext.utils

# Prevent accident import of an Ansible module from hanging on stdin read.
import ansible.module_utils.basic
ansible.module_utils.basic._ANSIBLE_ARGS = '{}'


class Exit(Exception):
    """
    Raised when a module exits with success.
    """
    def __init__(self, dct):
        self.dct = dct


class ModuleError(Exception):
    """
    Raised when a module voluntarily indicates failure via .fail_json().
    """
    def __init__(self, msg, dct):
        Exception.__init__(self, msg)
        self.dct = dct


def wtf_exit_json(self, **kwargs):
    """
    Replace AnsibleModule.exit_json() with something that doesn't try to
    suicide the process or JSON-encode the dictionary. Instead, cause Exit to
    be raised, with a `dct` attribute containing the successful result
    dictionary.
    """
    self.add_path_info(kwargs)
    kwargs.setdefault('changed', False)
    kwargs.setdefault('invocation', {
        'module_args': self.params
    })
    kwargs = ansible.module_utils.basic.remove_values(kwargs, self.no_log_values)
    self.do_cleanup_files()
    raise Exit(kwargs)


def wtf_fail_json(self, **kwargs):
    """
    Replace AnsibleModule.fail_json() with something that raises ModuleError,
    which includes a `dct` attribute.
    """
    self.add_path_info(kwargs)
    kwargs.setdefault('failed', True)
    kwargs.setdefault('invocation', {
        'module_args': self.params
    })
    kwargs = ansible.module_utils.basic.remove_values(kwargs, self.no_log_values)
    self.do_cleanup_files()
    raise ModuleError(kwargs.get('msg'), kwargs)


def run_module(module, raw_params=None, args=None):
    """
    Set up the process environment in preparation for running an Ansible
    module. The monkey-patches the Ansible libraries in various places to
    prevent it from trying to kill the process on completion, and to prevent it
    from reading sys.stdin.
    """
    if args is None:
        args = {}
    if raw_params is not None:
        args['_raw_params'] = raw_params

    ansible.module_utils.basic.AnsibleModule.exit_json = wtf_exit_json
    ansible.module_utils.basic.AnsibleModule.fail_json = wtf_fail_json
    ansible.module_utils.basic._ANSIBLE_ARGS = json.dumps({
        'ANSIBLE_MODULE_ARGS': args
    })

    try:
        mod = __import__(module, {}, {}, [''])
        # Ansible modules begin execution on import, because they're crap from
        # hell. Thus the above __import__ will cause either Exit or
        # ModuleError to be raised. If we reach the line below, the module did
        # not execute and must already have been imported for a previous
        # invocation, so we need to invoke main explicitly.
        mod.main()
    except Exit, e:
        return e.dct


def main(router):
    fmt = '%(asctime)s %(levelname).1s %(name)s: %(message)s'
    datefmt = '%H:%M:%S'
    level = logging.DEBUG
    level = logging.INFO
    logging.basicConfig(level=level, format=fmt, datefmt=datefmt)

    context = econtext.master.connect(broker)
    print context.call(run_module, 'ansible.modules.core.system.setup')
    for x in xrange(10):
        print context.call(run_module, 'ansible.modules.core.commands.command', 'hostname')

if __name__ == '__main__' and not econtext.slave:
    econtext.utils.run_with_router(main)
