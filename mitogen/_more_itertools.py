# SPDX-FileCopyrightText: 2012 Erik Rose
# SPDX-FileCopyrightText: 2025 Mitogen authors <https://github.com/mitogen-hq>
# SPDX-License-Identifier: MIT
# !mitogen: minify_safe
#
# Adapted from https://github.com/more-itertools/more-itertools/blob/v10.7.0/more_itertools/recipes.py

import itertools

from mitogen.core import next, zip


def sliding_window(it, size):
    """
    >>> list(sliding_window(range(6), 4))
    [(0, 1, 2, 3), (1, 2, 3, 4), (2, 3, 4, 5)]
    """
    its = itertools.tee(iter(it), size)
    for i, it in enumerate(its):
        next(itertools.islice(it, i, i), None)
    return zip(*its)


def transpose(it):
    """
    >>> list(transpose([(1, 2, 3), (11, 22, 33)]))
    [(1, 11), (2, 22), (3, 33)]
    """
    return zip(*it)
