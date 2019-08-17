
import functools
import re

import docutils.nodes
import docutils.utils


CUSTOM_RE = re.compile('(.*) <(.*)>')


def role(config, role, rawtext, text, lineno, inliner, options={}, content=[]):
    template = 'https://docs.ansible.com/ansible/latest/modules/%s_module.html'

    match = CUSTOM_RE.match(text)
    if match:  # "custom text <real link>"
        title = match.group(1)
        text = match.group(2)
    elif text.startswith('~'):  # brief
        text = text[1:]
        title = config.get('brief', '%s') % (
            docutils.utils.unescape(text),
        )
    else:
        title = config.get('text', '%s') % (
            docutils.utils.unescape(text),
        )

    node = docutils.nodes.reference(
        rawsource=rawtext,
        text=title,
        refuri=config['url'] % (text,),
        **options
    )

    return [node], []


def setup(app):
    for name, info in app.config._raw_config['domainrefs'].items():
        app.add_role(name, functools.partial(role, info))
