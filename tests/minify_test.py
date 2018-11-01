import glob

import unittest2

import mitogen.minify
import testlib


def read_sample(fname):
    sample_path = testlib.data_path('minimize_samples/' + fname)
    sample_file = open(sample_path)
    sample = sample_file.read()
    sample_file.close()
    return sample


class MinimizeSourceTest(unittest2.TestCase):
    func = staticmethod(mitogen.minify.minimize_source)

    def test_class(self):
        original = read_sample('class.py')
        expected = read_sample('class_min.py')
        self.assertEqual(expected, self.func(original))

    def test_comment(self):
        original = read_sample('comment.py')
        expected = read_sample('comment_min.py')
        self.assertEqual(expected, self.func(original))

    def test_def(self):
        original = read_sample('def.py')
        expected = read_sample('def_min.py')
        self.assertEqual(expected, self.func(original))

    def test_hashbang(self):
        original = read_sample('hashbang.py')
        expected = read_sample('hashbang_min.py')
        self.assertEqual(expected, self.func(original))

    def test_mod(self):
        original = read_sample('mod.py')
        expected = read_sample('mod_min.py')
        self.assertEqual(expected, self.func(original))

    def test_pass(self):
        original = read_sample('pass.py')
        expected = read_sample('pass_min.py')
        self.assertEqual(expected, self.func(original))

    def test_obstacle_course(self):
        original = read_sample('obstacle_course.py')
        expected = read_sample('obstacle_course_min.py')
        self.assertEqual(expected, self.func(original))


class MitogenCoreTest(unittest2.TestCase):
    # Verify minimize_source() succeeds for all built-in modules.
    func = staticmethod(mitogen.minify.minimize_source)

    def read_source(self, name):
        fp = open(name)
        try:
            return fp.read()
        finally:
            fp.close()

    def test_minify_all(self):
        for name in glob.glob('mitogen/*.py'):
            original = self.read_source(name)
            minified = self.func(original)
            compile(minified, name, 'exec')


if __name__ == '__main__':
    unittest2.main()
