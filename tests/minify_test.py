# SPDX-FileCopyrightText: 2017-2026 Mitogen authors <https://github.com/mitogen-hq>
# SPDX-License-Identifier: BSD-3-Clause

import glob
import pprint
import sys

import mitogen.minify
from mitogen.core import b

import testlib


class MinimizeSourceTest(testlib.TestCase):
    func = staticmethod(mitogen.minify.minimize_source)

    def test_class(self):
        original = testlib.read_bytes(testlib.data_path('minimize_samples/class.py'))
        expected = testlib.read_bytes(testlib.data_path('minimize_samples/class_min.py'))
        self.assertEqual(expected, self.func(original))

    def test_comment(self):
        original = testlib.read_bytes(testlib.data_path('minimize_samples/comment.py'))
        expected = testlib.read_bytes(testlib.data_path('minimize_samples/comment_min.py'))
        self.assertEqual(expected, self.func(original))

    def test_def(self):
        original = testlib.read_bytes(testlib.data_path('minimize_samples/def.py'))
        expected = testlib.read_bytes(testlib.data_path('minimize_samples/def_min.py'))
        self.assertEqual(expected, self.func(original))

    def test_hashbang(self):
        original = testlib.read_bytes(testlib.data_path('minimize_samples/hashbang.py'))
        expected = testlib.read_bytes(testlib.data_path('minimize_samples/hashbang_min.py'))
        self.assertEqual(expected, self.func(original))

    def test_mod(self):
        original = testlib.read_bytes(testlib.data_path('minimize_samples/mod.py'))
        expected = testlib.read_bytes(testlib.data_path('minimize_samples/mod_min.py'))
        self.assertEqual(expected, self.func(original))

    def test_pass(self):
        original = testlib.read_bytes(testlib.data_path('minimize_samples/pass.py'))
        expected = testlib.read_bytes(testlib.data_path('minimize_samples/pass_min.py'))
        self.assertEqual(expected, self.func(original))

    def test_obstacle_course(self):
        original = testlib.read_bytes(testlib.data_path('minimize_samples/obstacle_course.py'))
        expected = testlib.read_bytes(testlib.data_path('minimize_samples/obstacle_course_min.py'))
        self.assertEqual(expected, self.func(original))


class MitogenCoreTest(testlib.TestCase):
    # Verify minimize_source() succeeds for all built-in modules.
    func = staticmethod(mitogen.minify.minimize_source)

    def _test_syntax_valid(self, minified, name):
        compile(minified, name, 'exec')

    def _test_line_counts_match(self, original, minified):
        self.assertEqual(original.count(b('\n')), minified.count(b('\n')))

    def _test_non_blank_lines_match(self, name, original, minified):
        # Verify first token matches. We just want to ensure line numbers make
        # sense, this is good enough.
        olines = original.splitlines()
        mlines = minified.splitlines()
        for i, (orig, mini) in enumerate(zip(olines, mlines)):
            if i < 2 and orig.startswith(b('#')):
                self.assertEqual(orig, mini)
                continue

            owords = orig.split()
            mwords = mini.split()
            self.assertTrue(
                len(mwords) == 0 or (mwords[0] == owords[0]),
                pprint.pformat({
                    'line': i+1, 'name': name,
                    'owords': owords, 'mwords': mwords,
                }),
            )

    PY_24_25_SKIP = [
        # cProfile unsupported on 2.4, 2.6+ syntax is fine here.
        'mitogen/profiler.py',
    ]

    def test_minify_all(self):
        for name in glob.glob('mitogen/*.py') + glob.glob('mitogen/compat/*.py'):
            if name in self.PY_24_25_SKIP and sys.version_info < (2, 6):
                continue
            original = testlib.read_bytes(name)
            try:
                minified = self.func(original)
            except Exception:
                print('file was: ' + name)
                raise

            self._test_syntax_valid(minified, name)
            self._test_line_counts_match(original, minified)
            self._test_non_blank_lines_match(name, original, minified)
