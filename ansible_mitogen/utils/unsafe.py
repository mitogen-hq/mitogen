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
def _cast_unsafe(obj): return obj._strip_unsafe()
def _passthrough(obj): return obj


# A dispatch table to cast objects based on their exact type.
# This is an optimisation, reliable fallbacks are required (e.g. isinstance())
_CAST_DISPATCH = {
    bytes: bytes,
    dict: _cast_to_dict,
    list: _cast_to_list,
    tuple: _cast_to_list,
    mitogen.core.UnicodeType: mitogen.core.UnicodeType,
}
_CAST_DISPATCH.update({t: _passthrough for t in mitogen.utils.PASSTHROUGH})

if hasattr(ansible.utils.unsafe_proxy.AnsibleUnsafeText, '_strip_unsafe'):
    _CAST_DISPATCH.update({
        ansible.utils.unsafe_proxy.AnsibleUnsafeBytes: _cast_unsafe,
        ansible.utils.unsafe_proxy.AnsibleUnsafeText: _cast_unsafe,
        ansible.utils.unsafe_proxy.NativeJinjaUnsafeText: _cast_unsafe,
    })
elif ansible_mitogen.utils.ansible_version[:2] <= (2, 16):
    _CAST_DISPATCH.update({
        ansible.utils.unsafe_proxy.AnsibleUnsafeBytes: bytes,
        ansible.utils.unsafe_proxy.AnsibleUnsafeText: mitogen.core.UnicodeType,
    })
else:
    mitogen_ver = '.'.join(str(v) for v in mitogen.__version__)
    raise ImportError("Mitogen %s can't unwrap Ansible %s AnsibleUnsafe objects"
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
    if isinstance(obj, dict): return _cast_to_dict(obj)
    if isinstance(obj, (list, tuple)): return _cast_to_list(obj)

    return mitogen.utils.cast(obj)
