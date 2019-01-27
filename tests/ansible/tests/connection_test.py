
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
import ansible_mitogen.connection
import ansible_mitogen.plugins.connection.mitogen_local
import ansible_mitogen.process
import testlib


LOGGER_NAME = ansible_mitogen.target.LOG.name


# TODO: fixtureize
import mitogen.utils
mitogen.utils.log_to_file()
ansible_mitogen.process.MuxProcess.start(_init_logging=False)


class OptionalIntTest(unittest2.TestCase):
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


class ConnectionMixin(object):
    klass = ansible_mitogen.plugins.connection.mitogen_local.Connection

    def make_connection(self):
        play_context = ansible.playbook.play_context.PlayContext()
        return self.klass(play_context, new_stdin=False)

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


class PutDataTest(ConnectionMixin, unittest2.TestCase):
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


class PutFileTest(ConnectionMixin, unittest2.TestCase):
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
