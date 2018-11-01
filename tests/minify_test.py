import codecs
import glob
import pprint

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
        fp = codecs.open(name, encoding='utf-8')
        try:
            return fp.read()
        finally:
            fp.close()

    def _test_syntax_valid(self, minified, name):
        compile(minified, name, 'exec')

    def _test_line_counts_match(self, original, minified):
        self.assertEquals(original.count('\n'),
                          minified.count('\n'))

    def _test_non_blank_lines_match(self, name, original, minified):
        # Verify first token matches. We just want to ensure line numbers make
        # sense, this is good enough.
        olines = original.splitlines()
        mlines = minified.splitlines()
        for i, (orig, mini) in enumerate(zip(olines, mlines)):
            if i < 2:
                assert orig == mini
                continue

            owords = orig.split()
            mwords = mini.split()
            assert len(mwords) == 0 or (mwords[0] == owords[0]), pprint.pformat({
                'line': i+1,
                'filename': name,
                'owords': owords,
                'mwords': mwords,
            })

    def test_minify_all(self):
        for name in glob.glob('mitogen/*.py'):
            original = self.read_source(name)
            minified = self.func(original)

            self._test_syntax_valid(minified, name)
            self._test_line_counts_match(original, minified)
            self._test_non_blank_lines_match(name, original, minified)


if __name__ == '__main__':
    unittest2.main()
