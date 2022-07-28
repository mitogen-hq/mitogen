#!/usr/bin/env python2
# Copyright 2019, David Wilson
#
# Redistribution and use in source and binary forms, with or without
# modification, are permitted provided that the following conditions are met:
#
# 1. Redistributions of source code must retain the above copyright notice, this
# list of conditions and the following disclaimer.
#
# 2. Redistributions in binary form must reproduce the above copyright notice,
# this list of conditions and the following disclaimer in the documentation
# and/or other materials provided with the distribution.
#
# 3. Neither the name of the copyright holder nor the names of its contributors
# may be used to endorse or promote products derived from this software without
# specific prior written permission.
#
# THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS" AND
# ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE IMPLIED
# WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE
# DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT HOLDER OR CONTRIBUTORS BE LIABLE
# FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL
# DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR
# SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER
# CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY,
# OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE
# OF THIS SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.

import ast
import os

from setuptools import find_packages, setup

def parse_assignment(line, starts_with):
    if line.startswith(starts_with):
        _, _, s = line.partition('=')
        parts = ast.literal_eval(s.strip())
        return parts
    return None


def grep_version():
    path = os.path.join(os.path.dirname(__file__), 'mitogen/__init__.py')
    with open(path) as fp:
        for line in fp:
            parts = parse_assignment(line, '__version__')
            if parts:
                return '.'.join(map(str, parts))


def ansible_core_version():
    path = os.path.join(os.path.dirname(__file__), 'ansible_mitogen/loaders.py')
    min_version = None
    with open(path) as fp:
        for line in fp:
            ansible_version_min = parse_assignment(line, 'ANSIBLE_VERSION_MIN')
            if ansible_version_min:
                # ansible-core's minimum version is 2.11, older versions were
                # called ansible-base.
                if ansible_version_min == (2, 10):
                    ansible_version_min = (2, 11)
                min_version = '.'.join(map(str, ansible_version_min))
            ansible_version_max = parse_assignment(line, 'ANSIBLE_VERSION_MAX')
            if ansible_version_max:
                major, minor = ansible_version_max
                return (min_version, '{}.{}'.format(major, minor + 1))


def long_description():
    here = os.path.dirname(__file__)
    readme_path = os.path.join(here, 'README.md')
    with open(readme_path) as fp:
        readme = fp.read()
    return readme


setup(
    name = 'mitogen',
    version = grep_version(),
    description = 'Library for writing distributed self-replicating programs.',
    long_description = long_description(),
    long_description_content_type='text/markdown',
    author = 'David Wilson',
    license = 'New BSD',
    url = 'https://github.com/mitogen-hq/mitogen/',
    packages = find_packages(exclude=['tests', 'examples']),
    python_requires='>=2.7, !=3.0.*, !=3.1.*, !=3.2.*, !=3.3.*, !=3.4.*, !=3.5.*',
    zip_safe = False,
    classifiers = [
        'Environment :: Console',
        'Framework :: Ansible',
        'Intended Audience :: System Administrators',
        'License :: OSI Approved :: BSD License',
        'Operating System :: MacOS :: MacOS X',
        'Operating System :: POSIX',
        'Programming Language :: Python',
        'Programming Language :: Python :: 2.7',
        'Programming Language :: Python :: 3',
        'Programming Language :: Python :: 3.6',
        'Programming Language :: Python :: 3.7',
        'Programming Language :: Python :: 3.8',
        'Programming Language :: Python :: 3.9',
        'Programming Language :: Python :: 3.10',
        'Programming Language :: Python :: Implementation :: CPython',
        'Topic :: System :: Distributed Computing',
        'Topic :: System :: Systems Administration',
    ],
    extras_require = {
        'ansible-core': ['ansible-core>={},<{}'.format(*ansible_core_version())],
    },
)
