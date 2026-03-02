from __future__ import absolute_import
import io
import os
import stat
import sys
import tempfile
import unittest

if sys.version_info >= (3,):
    import configparser
    from unittest import mock
else:
    import ConfigParser as configparser
    import mock

import ansible.errors
import ansible.playbook.play_context

import mitogen.core

import ansible_mitogen.connection
import ansible_mitogen.plugins.connection.mitogen_local
import ansible_mitogen.process


def base_executable(executable=None):
    '''Return the path of the Python executable used to create the virtualenv.
    '''
    # https://docs.python.org/3/library/venv.html
    # https://github.com/pypa/virtualenv/blob/main/src/virtualenv/discovery/py_info.py
    # https://virtualenv.pypa.io/en/16.7.9/reference.html#compatibility-with-the-stdlib-venv-module
    if executable is None:
        executable = sys.executable

    if not executable:
        raise ValueError

    try:
        base_executable = sys._base_executable
    except AttributeError:
        base_executable = None

    if base_executable and base_executable != executable:
        return base_executable

    # Python 2.x only has sys.base_prefix if running outside a virtualenv.
    try:
        sys.base_prefix
    except AttributeError:
        # Python 2.x outside a virtualenv
        return executable

    # Python 3.3+ has sys.base_prefix. In a virtualenv it differs to sys.prefix.
    if sys.base_prefix == sys.prefix:
        return executable

    while executable.startswith(sys.prefix) and stat.S_ISLNK(os.lstat(executable).st_mode):
        dirname = os.path.dirname(executable)
        target = os.path.join(dirname, os.readlink(executable))
        executable = os.path.abspath(os.path.normpath(target))
        print(executable)

    if executable.startswith(sys.base_prefix):
        return executable

    # Virtualenvs record details in pyvenv.cfg
    parser = configparser.RawConfigParser()
    with io.open(os.path.join(sys.prefix, 'pyvenv.cfg'), encoding='utf-8') as f:
        content = u'[virtualenv]\n' + f.read()
    try:
        parser.read_string(content)
    except AttributeError:
        parser.readfp(io.StringIO(content))

    # virtualenv style pyvenv.cfg includes the base executable.
    # venv style pyvenv.cfg doesn't.
    try:
        return parser.get(u'virtualenv', u'base-executable')
    except configparser.NoOptionError:
        pass

    basename = os.path.basename(executable)
    home = parser.get(u'virtualenv', u'home')
    return os.path.join(home, basename)


class MuxProcessMixin(object):
    no_zombie_check = True

    @classmethod
    def setUpClass(cls):
        cls.model = ansible_mitogen.process.get_classic_worker_model(
            _init_logging=False
        )
        ansible_mitogen.process.set_worker_model(cls.model)
        cls.model.on_strategy_start()
        super(MuxProcessMixin, cls).setUpClass()

    @classmethod
    def tearDownClass(cls):
        cls.model._test_reset()
        super(MuxProcessMixin, cls).tearDownClass()


class ConnectionMixin(MuxProcessMixin):
    klass = ansible_mitogen.plugins.connection.mitogen_local.Connection

    def make_connection(self):
        play_context = ansible.playbook.play_context.PlayContext()
        conn = self.klass(play_context, new_stdin=False)
        # conn functions don't fetch ActionModuleMixin objs from _get_task_vars()
        # through the usual walk-the-stack approach so we'll not run interpreter discovery here
        conn._action = mock.MagicMock(
            _mitogen_interpreter_candidate=base_executable(),
        )
        conn.on_action_run(
            task_vars={},
            delegate_to_hostname=None,
            loader_basedir=None,
        )

        return conn

    def wait_for_completion(self):
        # put_data() is asynchronous, must wait for operation to happen. Do
        # that by making RPC for some junk that must run on the thread once op
        # completes.
        self.conn.get_chain().call(os.getpid)

    def setUp(self):
        super(ConnectionMixin, self).setUp()
        self.conn = self.make_connection()

    def tearDown(self):
        self.conn.close()
        super(ConnectionMixin, self).tearDown()


class MuxShutdownTest(ConnectionMixin, unittest.TestCase):
    def test_connection_failure_raised(self):
        # ensure if a WorkerProcess tries to connect to a MuxProcess that has
        # already shut down, it fails with a graceful error.
        path = self.model._muxes[0].path
        os.rename(path, path + '.tmp')
        try:
            #e = self.assertRaises(ansible.errors.AnsibleError,
                #lambda: self.conn._connect()
            #)
            e = 1
            print(e)
        finally:
            os.rename(path + '.tmp', path)


class OptionalIntTest(unittest.TestCase):
    func = staticmethod(ansible_mitogen.connection.optional_int)

    def test_already_int(self):
        self.assertEqual(0, self.func(0))
        self.assertEqual(1, self.func(1))
        self.assertEqual(-1, self.func(-1))

    def test_is_string(self):
        self.assertEqual(0, self.func("0"))
        self.assertEqual(1, self.func("1"))
        self.assertEqual(-1, self.func("-1"))

    def test_is_none(self):
        self.assertEqual(None, self.func(None))

    def test_is_junk(self):
        self.assertEqual(None, self.func({1:2}))


class FetchFileTest(ConnectionMixin, unittest.TestCase):
    def test_success(self):
        with tempfile.NamedTemporaryFile(prefix='mitotest') as ifp:
            with tempfile.NamedTemporaryFile(prefix='mitotest') as ofp:
                ifp.write(b'x' * (1048576 * 4))
                ifp.flush()
                ifp.seek(0)

                self.conn.fetch_file(ifp.name, ofp.name)
                # transfer_file() uses os.rename rather than direct data
                # overwrite, so we must reopen.
                with open(ofp.name, 'rb') as fp:
                    self.assertEqual(ifp.read(), fp.read())


class PutDataTest(ConnectionMixin, unittest.TestCase):
    def test_out_path(self):
        path = tempfile.mktemp(prefix='mitotest')
        contents = mitogen.core.b('contents')

        self.conn.put_data(path, contents)
        self.wait_for_completion()
        with open(path, 'rb') as f:
            self.assertEqual(contents, f.read())
        os.unlink(path)

    def test_mode(self):
        path = tempfile.mktemp(prefix='mitotest')
        contents = mitogen.core.b('contents')

        self.conn.put_data(path, contents, mode=int('0123', 8))
        self.wait_for_completion()
        st = os.stat(path)
        self.assertEqual(int('0123', 8), st.st_mode & int('0777', 8))
        os.unlink(path)


class PutFileTest(ConnectionMixin, unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        super(PutFileTest, cls).setUpClass()
        cls.big_path = tempfile.mktemp(prefix='mitotestbig')
        fp = open(cls.big_path, 'w')
        try:
            fp.write('x'*1048576)
        finally:
            fp.close()

    @classmethod
    def tearDownClass(cls):
        os.unlink(cls.big_path)
        super(PutFileTest, cls).tearDownClass()

    def test_out_path_tiny(self):
        path = tempfile.mktemp(prefix='mitotest')
        self.conn.put_file(in_path=__file__, out_path=path)
        self.wait_for_completion()
        with open(path, 'rb') as path_f:
            with open(__file__, 'rb') as __file__f:
                self.assertEqual(path_f.read(), __file__f.read())
        os.unlink(path)

    def test_out_path_big(self):
        path = tempfile.mktemp(prefix='mitotest')
        self.conn.put_file(in_path=self.big_path, out_path=path)
        self.wait_for_completion()
        with open(path, 'rb') as path_f:
            with open(self.big_path, 'rb') as big_path_f:
                self.assertEqual(path_f.read(), big_path_f.read())
        #self._compare_times_modes(path, __file__)
        os.unlink(path)

    def test_big_in_path_not_found(self):
        path = tempfile.mktemp(prefix='mitotest')
        self.assertRaises(ansible.errors.AnsibleFileNotFound,
            lambda: self.conn.put_file(in_path='/nonexistent', out_path=path))
