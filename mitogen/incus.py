# SPDX-FileCopyrightText: 2019 David Wilson
# SPDX-FileCopyrightText: 2026 Mitogen authors <https://github.com/mitogen-hq>
# SPDX-License-Identifier: BSD-3-Clause
# !mitogen: minify_safe

import mitogen.parent


class Options(mitogen.parent.Options):
    container = None
    incus_path = 'incus'
    python_path = 'python'

    def __init__(self, container, incus_path=None, **kwargs):
        super(Options, self).__init__(**kwargs)
        self.container = container
        if incus_path:
            self.incus_path = incus_path


class Connection(mitogen.parent.Connection):
    options_class = Options

    child_is_immediate_subprocess = False
    create_child_args = {
        # If incus finds any of stdin, stdout, stderr connected to a TTY, to
        # prevent input injection it creates a proxy pty, forcing all IO to be
        # buffered in <4KiB chunks. So ensure stderr is also routed to the
        # socketpair.
        'merge_stdio': True
    }

    eof_error_hint = (
        'Note: many versions of Incus do not report program execution failure '
        'meaningfully. Please check the host logs (/var/log) for more '
        'information.'
    )

    def _get_name(self):
        return u'incus.' + self.options.container

    def get_boot_command(self):
        bits = [
            self.options.incus_path,
            'exec',
            '--mode=non-interactive',
            self.options.container,
            '--',
        ]
        return bits + super(Connection, self).get_boot_command()
