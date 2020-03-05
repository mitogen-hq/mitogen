
from __future__ import absolute_import
import os
import os.path
import subprocess
import tempfile
import time

import unittest2

import mock
import ansible.errors
import ansible.playbook.play_context

import mitogen.core
import mitogen.utils

import ansible_mitogen.connection
import ansible_mitogen.plugins.connection.mitogen_local
import ansible_mitogen.process

import testlib


class MuxProcessMixin(object):
    no_zombie_check = True

    @classmethod
    def setUpClass(cls):
        #mitogen.utils.log_to_file()
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
        conn._action = mock.MagicMock(_possible_python_interpreter='/usr/bin/python')
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


class MuxShutdownTest(ConnectionMixin, testlib.TestCase):
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


class OptionalIntTest(testlib.TestCase):
    func = staticmethod(ansible_mitogen.connection.optional_int)

    def test_already_int(self):
        self.assertEquals(0, self.func(0))
        self.assertEquals(1, self.func(1))
        self.assertEquals(-1, self.func(-1))

    def test_is_string(self):
        self.assertEquals(0, self.func("0"))
        self.assertEquals(1, self.func("1"))
        self.assertEquals(-1, self.func("-1"))

    def test_is_none(self):
        self.assertEquals(None, self.func(None))

    def test_is_junk(self):
        self.assertEquals(None, self.func({1:2}))


class FetchFileTest(ConnectionMixin, testlib.TestCase):
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
                    self.assertEquals(ifp.read(), fp.read())


class PutDataTest(ConnectionMixin, testlib.TestCase):
    def test_out_path(self):
        path = tempfile.mktemp(prefix='mitotest')
        contents = mitogen.core.b('contents')

        self.conn.put_data(path, contents)
        self.wait_for_completion()
        self.assertEquals(contents, open(path, 'rb').read())
        os.unlink(path)

    def test_mode(self):
        path = tempfile.mktemp(prefix='mitotest')
        contents = mitogen.core.b('contents')

        self.conn.put_data(path, contents, mode=int('0123', 8))
        self.wait_for_completion()
        st = os.stat(path)
        self.assertEquals(int('0123', 8), st.st_mode & int('0777', 8))
        os.unlink(path)


class PutFileTest(ConnectionMixin, testlib.TestCase):
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
        self.assertEquals(open(path, 'rb').read(),
                          open(__file__, 'rb').read())

        os.unlink(path)

    def test_out_path_big(self):
        path = tempfile.mktemp(prefix='mitotest')
        self.conn.put_file(in_path=self.big_path, out_path=path)
        self.wait_for_completion()
        self.assertEquals(open(path, 'rb').read(),
                          open(self.big_path, 'rb').read())
        #self._compare_times_modes(path, __file__)
        os.unlink(path)

    def test_big_in_path_not_found(self):
        path = tempfile.mktemp(prefix='mitotest')
        self.assertRaises(ansible.errors.AnsibleFileNotFound,
            lambda: self.conn.put_file(in_path='/nonexistent', out_path=path))


if __name__ == '__main__':
    unittest2.main()
