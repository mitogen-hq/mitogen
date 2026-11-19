# coding: utf-8
# SPDX-FileCopyrightText: 2017-2026 Mitogen authors <https://github.com/mitogen-hq>
# SPDX-License-Identifier: BSD-3-Clause
# !mitogen: minify_safe

import sys

if sys.version_info >= (3, 0):
    import tokenize
else:
    import mitogen.compat.tokenize as tokenize

import mitogen.core


def minimize_source(source):
    """
    Remove comments and docstrings from Python `source`, preserving line
    numbers and syntax of empty blocks.

    :param bytes source:
        The source to minimize.

    :returns bytes:
        The minimized source.
    """
    tokens = tokenize.tokenize(mitogen.core.BytesIO(source).readline)
    tokens = strip_comments(tokens)
    tokens = strip_docstrings(tokens)
    tokens = reindent(tokens)
    return tokenize.untokenize(tokens)


def strip_comments(tokens):
    """
    Drop comment tokens from a `tokenize` stream.

    Comments on lines 1-2 are kept, to preserve hashbang and encoding.
    Trailing whitespace is remove from all lines.
    """
    prev_typ = None
    prev_end_col = 0
    for typ, tok, (start_row, start_col), (end_row, end_col), line in tokens:
        if typ in (tokenize.NL, tokenize.NEWLINE):
            if prev_typ in (tokenize.NL, tokenize.NEWLINE):
                start_col = 0
            else:
                start_col = prev_end_col
            end_col = start_col + 1
        elif typ == tokenize.COMMENT and start_row > 2:
            continue
        prev_typ = typ
        prev_end_col = end_col
        yield typ, tok, (start_row, start_col), (end_row, end_col), line


def strip_docstrings(tokens):
    """
    Replace docstring tokens with NL tokens in a `tokenize` stream.

    Any STRING token not part of an expression is deemed a docstring.
    Indented docstrings are not yet recognised.
    """
    PASSTHROUGHS = frozenset((tokenize.COMMENT, tokenize.ENCODING, tokenize.NL))
    STACKERS = frozenset((tokenize.DEDENT, tokenize.INDENT, tokenize.STRING))
    WAIT_NEWLINE = 0
    WAIT_STRING = 1
    stack = []
    state = WAIT_STRING
    for t in tokens:
        typ = t[0]
        if state == WAIT_STRING:
            if typ in PASSTHROUGHS:
                yield t
            elif typ in STACKERS:
                stack.append(t)
            elif typ == tokenize.NEWLINE:
                stack.append(t)
                start_line, end_line = stack[0][2][0], stack[-1][3][0]+1
                for i in mitogen.core.range(start_line, end_line):
                    yield tokenize.NL, '\n', (i, 0), (i,1), '\n'
                for t in stack:
                    if t[0] in (tokenize.DEDENT, tokenize.INDENT):
                        yield t[0], t[1], (i+1, t[2][1]), (i+1, t[3][1]), t[4]
                del stack[:]
            else:
                stack.append(t)
                for t in stack: yield t
                del stack[:]
                state = WAIT_NEWLINE
        elif state == WAIT_NEWLINE:
            if typ == tokenize.NEWLINE:
                state = WAIT_STRING
            yield t


def reindent(tokens, indent=' '):
    """
    Replace existing indentation in a token steam, with `indent`.
    """
    old_levels = []
    old_level = 0
    new_level = 0
    for typ, tok, (start_row, start_col), (end_row, end_col), line in tokens:
        if typ == tokenize.INDENT:
            old_levels.append(old_level)
            old_level = len(tok)
            new_level += 1
            tok = indent * new_level
        elif typ == tokenize.DEDENT:
            old_level = old_levels.pop()
            new_level -= 1
        start_col = max(0, start_col - old_level + new_level)
        if start_row == end_row:
            end_col = start_col + len(tok)
        yield typ, tok, (start_row, start_col), (end_row, end_col), line
