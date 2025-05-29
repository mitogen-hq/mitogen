from __future__ import absolute_import, division, print_function
__metaclass__ = type

import ansible
import ansible.utils.unsafe_proxy

import ansible_mitogen.utils

import mitogen
import mitogen.core
import mitogen.utils

__all__ = [
    'cast',
]

def _cast_to_dict(obj): return {cast(k): cast(v) for k, v in obj.items()}
def _cast_to_list(obj): return [cast(v) for v in obj]
def _cast_to_set(obj): return set(cast(v) for v in obj)
def _cast_to_tuple(obj): return tuple(cast(v) for v in obj)
def _cast_unsafe(obj): return obj._strip_unsafe()
def _passthrough(obj): return obj
def _untag(obj): return obj._native_copy()


# A dispatch table to cast objects based on their exact type.
# This is an optimisation, reliable fallbacks are required (e.g. isinstance())
_CAST_DISPATCH = {
    bytes: bytes,
    dict: _cast_to_dict,
    list: _cast_to_list,
    mitogen.core.UnicodeType: mitogen.core.UnicodeType,
}
_CAST_DISPATCH.update({t: _passthrough for t in mitogen.utils.PASSTHROUGH})

_CAST_SUBTYPES = [
    dict,
    list,
]

if hasattr(ansible.utils.unsafe_proxy, 'TrustedAsTemplate'):
    import datetime
    import ansible.module_utils._internal._datatag
    _CAST_DISPATCH.update({
        set: _cast_to_set,
        tuple: _cast_to_tuple,
        ansible.module_utils._internal._datatag._AnsibleTaggedBytes: _untag,
        ansible.module_utils._internal._datatag._AnsibleTaggedDate: _untag,
        ansible.module_utils._internal._datatag._AnsibleTaggedDateTime: _untag,
        ansible.module_utils._internal._datatag._AnsibleTaggedDict: _cast_to_dict,
        ansible.module_utils._internal._datatag._AnsibleTaggedFloat: _untag,
        ansible.module_utils._internal._datatag._AnsibleTaggedInt: _untag,
        ansible.module_utils._internal._datatag._AnsibleTaggedList: _cast_to_list,
        ansible.module_utils._internal._datatag._AnsibleTaggedSet: _cast_to_set,
        ansible.module_utils._internal._datatag._AnsibleTaggedStr: _untag,
        ansible.module_utils._internal._datatag._AnsibleTaggedTime: _untag,
        ansible.module_utils._internal._datatag._AnsibleTaggedTuple: _cast_to_tuple,
        ansible.utils.unsafe_proxy.AnsibleUnsafeBytes: bytes,
        ansible.utils.unsafe_proxy.AnsibleUnsafeText: mitogen.core.UnicodeType,
        datetime.date: _passthrough,
        datetime.datetime: _passthrough,
        datetime.time: _passthrough,
    })
    _CAST_SUBTYPES.extend([
        set,
        tuple,
    ])
elif hasattr(ansible.utils.unsafe_proxy.AnsibleUnsafeText, '_strip_unsafe'):
    _CAST_DISPATCH.update({
        tuple: _cast_to_list,
        ansible.utils.unsafe_proxy.AnsibleUnsafeBytes: _cast_unsafe,
        ansible.utils.unsafe_proxy.AnsibleUnsafeText: _cast_unsafe,
        ansible.utils.unsafe_proxy.NativeJinjaUnsafeText: _cast_unsafe,
    })
    _CAST_SUBTYPES.extend([
        tuple,
    ])
elif ansible_mitogen.utils.ansible_version[:2] <= (2, 16):
    _CAST_DISPATCH.update({
        tuple: _cast_to_list,
        ansible.utils.unsafe_proxy.AnsibleUnsafeBytes: bytes,
        ansible.utils.unsafe_proxy.AnsibleUnsafeText: mitogen.core.UnicodeType,
    })
    _CAST_SUBTYPES.extend([
        tuple,
    ])
else:
    mitogen_ver = '.'.join(str(v) for v in mitogen.__version__)
    raise ImportError("Mitogen %s can't cast Ansible %s objects"
                      % (mitogen_ver, ansible.__version__))


def cast(obj):
    """
    Return obj (or a copy) with subtypes of builtins cast to their supertype.

    This is an enhanced version of :func:`mitogen.utils.cast`. In addition it
    handles ``ansible.utils.unsafe_proxy.AnsibleUnsafeText`` and variants.

    There are types handled by :func:`ansible.utils.unsafe_proxy.wrap_var()`
    that this function currently does not handle (e.g. `set()`), or preserve
    preserve (e.g. `tuple()`). Future enhancements may change this.

    :param obj:
        Object to undecorate.
    :returns:
        Undecorated object.
    """
    # Fast path: obj is a known type, dispatch directly
    try:
        unwrapper = _CAST_DISPATCH[type(obj)]
    except KeyError:
        pass
    else:
        return unwrapper(obj)

    # Slow path: obj is some unknown subclass
    for typ_ in _CAST_SUBTYPES:
        if isinstance(obj, typ_):
            unwrapper = _CAST_DISPATCH[typ_]
            return unwrapper(obj)

    return mitogen.utils.cast(obj)
