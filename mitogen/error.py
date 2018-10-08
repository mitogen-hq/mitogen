# Copyright 2017, David Wilson
#
# Redistribution and use in source and binary forms, with or without
# modification, are permitted provided that the following conditions are met:
#
# 1. Redistributions of source code must retain the above copyright notice,
# this list of conditions and the following disclaimer.
#
# 2. Redistributions in binary form must reproduce the above copyright notice,
# this list of conditions and the following disclaimer in the documentation
# and/or other materials provided with the distribution.
#
# 3. Neither the name of the copyright holder nor the names of its contributors
# may be used to endorse or promote products derived from this software without
# specific prior written permission.
#
# THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS"
# AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE
# IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE
# ARE DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT HOLDER OR CONTRIBUTORS BE
# LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR
# CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF
# SUBSTITUTE GOODS OR SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS
# INTERRUPTION) HOWEVER CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN
# CONTRACT, STRICT LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE)
# ARISING IN ANY WAY OUT OF THE USE OF THIS SOFTWARE, EVEN IF ADVISED OF THE
# POSSIBILITY OF SUCH DAMAGE.

"""
This defines :func:`match` that produces dynamic subclasses of a magical type
whose :func:`isinstance` returns :data:`True` if the instance being checked is
a :class:`mitogen.core.CallError` whose original exception type matches a
parent class in the hierarchy of the the supplied Exception type.
"""

from __future__ import absolute_import
import sys

import mitogen.core


#: Map Exception class -> dynamic CallError subclass.
_error_by_cls = {}



def find_class_by_qualname(s):
    modname, sep, classname = s.rpartition('.')
    if not sep:
        return None

    module = sys.modules.get(modname)
    if module is None:
        return None

    return getattr(module, classname, None)


def for_type(cls):
    try:
        return _error_by_cls[cls]
    except KeyError:
        pass

    bases = tuple(for_type(c) for c in cls.__bases__
                  if c is not object)

    type_name = mitogen.core.qualname(cls)
    klass = type('CallError_' + type_name, bases, {
        'type_name': type_name,
    })
    _error_by_cls[cls] = klass
    print [klass, klass.__bases__]
    return klass



def for_type_name(type_name):
    cls = find_class_by_qualname(type_name)
    if cls:
        return for_type(cls)
    return mitogen.core.CallError

mitogen.core.CallError.for_type_name = staticmethod(for_type_name)


def match(target_cls):
    """
    Return a magic for use in :keyword:`except` statements that matches any
    :class:`mitogen.core.CallError` whose original exception type was
    `target_cls` or one of its base classes::

        try:
            context.call(func_raising_some_exc)
        except mitogen.error.match(ValueError) as e:
            # handle ValueError.
            pass

    :param type target_cls:
        Target class to match.

    :returns:
        :class:`Matcher` subclass.
    """
    return for_type(target_cls)
    try:
        return _matcher_by_cls[target_cls]
    except KeyError:
        name = '%s{%s}' % (
            mitogen.core.qualname(Matcher),
            mitogen.core.qualname(target_cls),
        )
        matcher_cls = type(name, (Matcher,), {
            'type_names': frozenset(
                mitogen.core.qualname(cls)
                for cls in get_matching_classes(target_cls)
            )
        })
        _matcher_by_cls[target_cls] = matcher_cls
        return matcher_cls
