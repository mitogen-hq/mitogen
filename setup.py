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

import os
import re

from setuptools import find_packages, setup


def grep_version():
    # See also changlelog_version() in docs.conf.py
    path = os.path.join(os.path.dirname(__file__), 'mitogen/__init__.py')

    # Based on https://packaging.python.org/en/latest/specifications/version-specifiers/#appendix-parsing-version-strings-with-regular-expressions
    # e.g. "__version__ = (0, 1, 2)", "__version__ = (0, 1, 3, 'dev')",
    #      "__version__ = (0, 1, 4, 'a', 1)"
    version_pattern = re.compile(
        r'''
        ^__version__\s=\s\(
        (?P<major>\d+)
        ,\s
        (?P<minor>\d+)
        ,\s
        (?P<patch>\d+)
        (?:
            (?:,\s '(?P<dev_l>dev)')
            | (?:,\s '(?P<pre_l>a|b)' ,\s (?P<pre_n>\d+))
        )?
        \)
        $
        ''',
        re.MULTILINE | re.VERBOSE,
    )
    with open(path) as fp:
        match = version_pattern.search(fp.read())
    if match is None:
        raise ValueError('Could not find __version__ string in %s', path)
    # e.g. '0.1.2', '0.1.3dev', '0.1.4a1'
    return '.'.join(str(part) for part in match.groups() if part)


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
        'Programming Language :: Python :: 3.11',
        'Programming Language :: Python :: 3.12',
        'Programming Language :: Python :: 3.13',
        'Programming Language :: Python :: Implementation :: CPython',
        'Topic :: System :: Distributed Computing',
        'Topic :: System :: Systems Administration',
    ],
)
