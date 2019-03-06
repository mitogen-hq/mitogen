# I am an Ansible action plug-in. I run the script provided in the parameter in
# the context of the action.

import sys

from ansible.plugins.action import ActionBase


def execute(s, gbls, lcls):
    if sys.version_info > (3,):
        exec(s, gbls, lcls)
    else:
        exec('exec s in gbls, lcls')


class ActionModule(ActionBase):
    def run(self, tmp=None, task_vars=None):
        super(ActionModule, self).run(tmp=tmp, task_vars=task_vars)

        lcls = {}
        # Capture keys to remove later, including any crap Python adds.
        execute('pass', globals(), lcls)
        lcls['self'] = self
        # Old mitogen_action_script used explicit result dict.
        lcls['result'] = lcls

        pre_keys = list(lcls)
        execute(self._task.args['script'], globals(), lcls)

        for key in pre_keys:
            del lcls[key]
        return lcls


if __name__ == '__main__':
    main()
