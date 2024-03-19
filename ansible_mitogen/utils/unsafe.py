from __future__ import absolute_import, division, print_function
__metaclass__ = type

import ansible.module_utils.common._collections_compat as collections_abc
import ansible.utils.unsafe_proxy

import mitogen.core

try:
    from ansible.utils.native_jinja import NativeJinjaText
    from ansible.utils.unsafe_proxy import NativeJinjaUnsafeText
except ImportError:
    class NativeJinjaText(object): pass
    class NativeJinjaUnsafeText(object): pass

__all__ = [
    'unwrap_vars',
]


if hasattr(ansible.utils.unsafe_proxy.AnsibleUnsafeText, '_strip_unsafe'):
    def _unwrap_unsafe(v):
        "Return v, cast to its base type if v is a subtype of AnsibleUnsafe."
        return v._strip_unsafe()
else:
    def _unwrap_unsafe(v):
        "Return v, cast to its base type if v is a subtype of AnsibleUnsafe."
        if isinstance(v, NativeJinjaUnsafeText):
            return NativeJinjaText(v)
        if isinstance(v, ansible.utils.unsafe_proxy.AnsibleUnsafeText):
            return mitogen.core.UnicodeType(v)
        if isinstance(v, ansible.utils.unsafe_proxy.AnsibleUnsafeBytes):
            return mitogen.core.BytesType(v)
        raise TypeError("Unknown AnsibleUnsafe subtype: %s" % (type(v),))

def _unwrap_dict(v):
    return {unwrap_var(k): unwrap_var(v_) for k, v_ in v.items()}

def _passthrough(v):
    return v

def _unwrap_sequence(v):
    v_type = type(v)
    return v_type(unwrap_var(k) for k in v)

def _unwrap_set(v):
    return {unwrap_var(k) for k in v}

_KNOWN_TYPE_UNWRAPPERS = {
    bool: bool,
    bytes: bytes,
    complex: complex,
    dict: _unwrap_dict,
    float: float,
    frozenset: _unwrap_set,
    int: int, 
    list: _unwrap_sequence,
    mitogen.core.long: mitogen.core.long,
    type(None): _passthrough,
    set: _unwrap_set,
    tuple: _unwrap_sequence,
    mitogen.core.UnicodeType: mitogen.core.UnicodeType,
    ansible.utils.unsafe_proxy.AnsibleUnsafeBytes: _unwrap_unsafe,
    ansible.utils.unsafe_proxy.AnsibleUnsafeText: _unwrap_unsafe,
    NativeJinjaUnsafeText: _unwrap_unsafe,
    mitogen.core.Blob: _passthrough,
    mitogen.core.CallError: _passthrough,
    mitogen.core.Context: _passthrough,
    mitogen.core.Secret: _passthrough,
}

def unwrap_var(v):
    # Fast path: v is a well known type, needs only a single dict lookup
    try:
        unwrapper = _KNOWN_TYPE_UNWRAPPERS[type(v)]
    except KeyError:
        pass
    else:
        return unwrapper(v)

    # Slow path: v is some unknown subclass
    if isinstance(v, ansible.utils.unsafe_proxy.AnsibleUnsafe):
        return _unwrap_unsafe(v)
    if isinstance(v, bytes):
        return bytes(v)
    if isinstance(v, mitogen.core.UnicodeType):
        return mitogen.core.UnicodeType(v)
    if isinstance(v, collections_abc.Mapping):
        return _unwrap_dict(v)
    if isinstance(v, collections_abc.Set):
        return _unwrap_set(v)
    if isinstance(v, collections_abc.Sequence):
        return _unwrap_sequence(v)

    return v    
