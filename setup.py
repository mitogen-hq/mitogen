#!/usr/bin/env python2

from distutils.core import setup

setup(
    name = 'mitogen',
    version = '0.0.0',
    description = 'Library for writing distributed self-replicating programs. THIS PACKAGE IS INCOMPLETE. IT IS BEING UPLOADED BECAUSE PYPI MAINTAINERS BROKE THE REGISTER COMMAND',
    author = 'David Wilson',
    license = 'OpenLDAP BSD',
    url = 'http://github.com/dw/mitogen/',
    packages = ['mitogen'],
    zip_safe = False,
    classifiers = [
        'Development Status :: 3 - Alpha',
        'Environment :: Console',
        'Intended Audience :: System Administrators',
        'License :: OSI Approved :: BSD License',
        'Operating System :: POSIX',
        'Programming Language :: Python',
        'Programming Language :: Python :: 2.4',
        'Programming Language :: Python :: 2.5',
        'Programming Language :: Python :: 2.6',
        'Programming Language :: Python :: 2.7',
        'Programming Language :: Python :: 2 :: Only',
        'Programming Language :: Python :: Implementation :: CPython',
        'Topic :: System :: Distributed Computing',
        'Topic :: System :: Systems Administration',
    ],
)
