from ansible.module_utils._text import to_text


try:
    Unicode = unicode
except:
    Unicode = str


def to_text(s):
    """
    Ensure the str or unicode `s` is unicode, and strip away any subclass. Also
    works on lists.
    """
    if isinstance(s, list):
        return [to_text(ss) for ss in s]
    if not isinstance(s, Unicode):
        s = to_text(s)
    return Unicode(s)


class FilterModule(object):
    def filters(self):
        return {
            'to_text': to_text,
        }
