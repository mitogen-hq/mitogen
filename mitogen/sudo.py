# Copyright 2019, David Wilson
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

# !mitogen: minify_safe

import logging
import optparse
import re

import mitogen.core
import mitogen.parent


LOG = logging.getLogger(__name__)

password_incorrect_msg = 'sudo password is incorrect'
password_required_msg = 'sudo password is required'

# See https://github.com/mitogen-hq/mitogen/wiki/Sudo-notes#password-prompt
PASSWORD_PROMPT = 'mitogen-sudo-prompt:'
PASSWORD_PROMPT_RE = re.compile(
    mitogen.core.b(
        r'''
        # sudo.ws, uses -p/--prompt argument as is.
        mitogen-sudo-prompt:\Z
        # sudo-rs, adds a prefix & suffix to the -p/--prompt argument.
        | \[sudo:\ mitogen-sudo-prompt:\]\ [^*\n]{1,50}?\Z
        '''
    ),
    re.VERBOSE,
)

SUDO_OPTIONS = [
    #(False, 'bool', '--askpass', '-A')
    #(False, 'str', '--auth-type', '-a')
    #(False, 'bool', '--background', '-b')
    #(False, 'str', '--close-from', '-C')
    #(False, 'str', '--login-class', 'c')
    (True,  'bool', '--preserve-env', '-E'),
    #(False, 'bool', '--edit', '-e')
    #(False, 'str', '--group', '-g')
    (True,  'bool', '--set-home', '-H'),
    #(False, 'str', '--host', '-h')
    (False, 'bool', '--login', '-i'),
    #(False, 'bool', '--remove-timestamp', '-K')
    #(False, 'bool', '--reset-timestamp', '-k')
    #(False, 'bool', '--list', '-l')
    #(False, 'bool', '--preserve-groups', '-P')
    #(False, 'str', '--prompt', '-p')

    # SELinux options. Passed through as-is.
    (False, 'str', '--role', '-r'),
    (False, 'str', '--type', '-t'),

    # These options are supplied by default by Ansible, but are ignored, as
    # sudo always runs under a TTY with Mitogen.
    (True, 'bool', '--stdin', '-S'),
    (True, 'bool', '--non-interactive', '-n'),

    #(False, 'str', '--shell', '-s')
    #(False, 'str', '--other-user', '-U')
    (False, 'str', '--user', '-u'),
    #(False, 'bool', '--version', '-V')
    #(False, 'bool', '--validate', '-v')
]


class OptionParser(optparse.OptionParser):
    def help(self):
        self.exit()
    def error(self, msg):
        self.exit(msg=msg)
    def exit(self, status=0, msg=None):
        msg = 'sudo: ' + (msg or 'unsupported option')
        raise mitogen.core.StreamError(msg)


def make_sudo_parser():
    parser = OptionParser()
    for supported, kind, longopt, shortopt in SUDO_OPTIONS:
        if kind == 'bool':
            parser.add_option(longopt, shortopt, action='store_true')
        else:
            parser.add_option(longopt, shortopt)
    return parser


def parse_sudo_flags(args):
    parser = make_sudo_parser()
    opts, args = parser.parse_args(args)
    if len(args):
        raise mitogen.core.StreamError('unsupported sudo arguments:'+str(args))
    return opts


class PasswordError(mitogen.core.StreamError):
    pass


def option(default, *args):
    for arg in args:
        if arg is not None:
            return arg
    return default


class Options(mitogen.parent.Options):
    sudo_path = 'sudo'
    username = 'root'
    password = None
    preserve_env = False
    set_home = False
    login = False

    selinux_role = None
    selinux_type = None

    def __init__(self, username=None, sudo_path=None, password=None,
                 preserve_env=None, set_home=None, sudo_args=None,
                 login=None, selinux_role=None, selinux_type=None, **kwargs):
        super(Options, self).__init__(**kwargs)
        opts = parse_sudo_flags(sudo_args or [])

        self.username = option(self.username, username, opts.user)
        self.sudo_path = option(self.sudo_path, sudo_path)
        if password:
            self.password = mitogen.core.to_text(password)
        self.preserve_env = option(self.preserve_env,
            preserve_env, opts.preserve_env)
        self.set_home = option(self.set_home, set_home, opts.set_home)
        self.login = option(self.login, login, opts.login)
        self.selinux_role = option(self.selinux_role, selinux_role, opts.role)
        self.selinux_type = option(self.selinux_type, selinux_type, opts.type)


class SetupProtocol(mitogen.parent.RegexProtocol):
    password_sent = False

    def _on_password_prompt(self, line, match):
        LOG.debug('%s: (password prompt): %s',
            self.stream.name, line.decode('utf-8', 'replace'))

        if self.stream.conn.options.password is None:
            self.stream.conn._fail_connection(
                PasswordError(password_required_msg)
            )
            return

        if self.password_sent:
            self.stream.conn._fail_connection(
                PasswordError(password_incorrect_msg)
            )
            return

        self.stream.transmit_side.write(
            (self.stream.conn.options.password + '\n').encode('utf-8')
        )
        self.password_sent = True

    PARTIAL_PATTERNS = [
        (PASSWORD_PROMPT_RE, _on_password_prompt),
    ]


class Connection(mitogen.parent.Connection):
    diag_protocol_class = SetupProtocol
    options_class = Options
    create_child = staticmethod(mitogen.parent.hybrid_tty_create_child)
    create_child_args = {
        'escalates_privilege': True,
    }
    child_is_immediate_subprocess = False

    def _get_name(self):
        return u'sudo.' + mitogen.core.to_text(self.options.username)

    def get_boot_command(self):
        # Note: sudo did not introduce long-format option processing until July
        # 2013, so even though we parse long-format options, supply short-form
        # to the sudo command.
        boot_cmd = super(Connection, self).get_boot_command()

        bits = [
            self.options.sudo_path,
            '-p', PASSWORD_PROMPT,
            '-u', self.options.username,
        ]
        if self.options.preserve_env:
            bits += ['-E']
        if self.options.set_home:
            bits += ['-H']
        if self.options.login:
            bits += ['-i']
        if self.options.selinux_role:
            bits += ['-r', self.options.selinux_role]
        if self.options.selinux_type:
            bits += ['-t', self.options.selinux_type]

        # special handling for bash builtins
        # TODO: more efficient way of doing this, at least
        # it's only 1 iteration of boot_cmd to go through
        source_found = False
        for cmd in boot_cmd[:]:
            # rip `source` from boot_cmd if it exists; sudo.py can't run this
            # even with -i or -s options
            # since we've already got our ssh command working we shouldn't
            # need to source anymore
            # couldn't figure out how to get this to work using sudo flags
            if 'source' == cmd:
                boot_cmd.remove(cmd)
                source_found = True
                continue
            if source_found:
                # remove words until we hit the python interpreter call
                if not cmd.endswith('python'):
                    boot_cmd.remove(cmd)
                else:
                    break

        return bits + ['--'] + boot_cmd
