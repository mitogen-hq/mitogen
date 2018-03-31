import unittest2

from mitogen.parent import minimize_source

import testlib


def read_sample(fname):
    sample_path = testlib.data_path('minimize_samples/' + fname)
    sample_file = open(sample_path)
    sample = sample_file.read()
    sample_file.close()
    return sample


class MinimizeSource(unittest2.TestCase):
    def test_class(self):
        original = read_sample('class.py')
        minimized = read_sample('class_min.py')
        self.assertEquals(minimized, minimize_source(original))


    def test_def(self):
        original = read_sample('def.py')
        minimized = read_sample('def_min.py')
        self.assertEquals(minimized, minimize_source(original))

    def test_hashbang(self):
        original = read_sample('hashbang.py')
        minimized = read_sample('hashbang_min.py')
        self.assertEquals(minimized, minimize_source(original))

    def test_mod(self):
        original = read_sample('mod.py')
        minimized = read_sample('mod_min.py')
        self.assertEquals(minimized, minimize_source(original))

    def test_obstacle_course(self):
        original = read_sample('obstacle_course.py')
        minimized = read_sample('obstacle_course_min.py')
        self.assertEquals(minimized, minimize_source(original))


if __name__ == '__main__':
    unittest2.main()
