import os
import tempfile

import testlib

from mitogen.core import b
import ansible_mitogen.runner


klass = ansible_mitogen.runner.EnvironmentFileWatcher
environb = getattr(os, 'environb', os.environ)


class WatcherTest(testlib.TestCase):
    def setUp(self):
        self.original_env = environb.copy()
        self.tf = tempfile.NamedTemporaryFile()

    def tearDown(self):
        self.tf.close()
        environb.clear()
        environb.update(self.original_env)

    def test_missing_file(self):
        # just ensure it doesn't crash
        watcher = klass('/nonexistent')
        watcher.check()

    def test_file_becomes_missing(self):
        # just ensure it doesn't crash
        watcher = klass(self.tf.name)
        watcher.check()
        os.unlink(self.tf.name)
        watcher.check()
        open(self.tf.name,'wb').close()

    def test_key_deleted(self):
        environb[b('SOMEKEY')] = b('123')
        self.tf.write(b('SOMEKEY=123\n'))
        self.tf.flush()
        watcher = klass(self.tf.name)
        self.tf.seek(0)
        self.tf.truncate(0)
        watcher.check()
        self.assertTrue(b('SOMEKEY') not in environb)

    def test_key_added(self):
        watcher = klass(self.tf.name)
        self.tf.write(b('SOMEKEY=123\n'))
        self.tf.flush()
        watcher.check()
        self.assertEqual(environb[b('SOMEKEY')], b('123'))

    def test_key_shadowed_nuchange(self):
        environb[b('SOMEKEY')] = b('234')
        self.tf.write(b('SOMEKEY=123\n'))
        self.tf.flush()
        watcher = klass(self.tf.name)
        watcher.check()
        self.assertEqual(environb[b('SOMEKEY')], b('234'))

    def test_binary_key_added(self):
        watcher = klass(self.tf.name)
        self.tf.write(b('SOMEKEY=\xff\xff\xff\n'))
        self.tf.flush()
        watcher.check()
        self.assertEqual(environb[b('SOMEKEY')], b('\xff\xff\xff'))
