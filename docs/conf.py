import re
import sys

sys.path.append('.')


def changelog_version(path, encoding='utf-8'):
    "Return the 1st *stable* (not pre, dev) version in the changelog"
    # See also grep_version() in setup.py
    # e.g. "0.1.2, (1999-12-31)\n"
    version_pattern = re.compile(
        r'^v(?P<version>\d+\.\d+\.\d+) \((?P<date>\d\d\d\d-\d\d-\d\d)\)$',
        re.MULTILINE,
    )

    with open(path, encoding=encoding) as f:
        match = version_pattern.search(f.read())
        return match.group('version')


VERSION = changelog_version('changelog.rst')

author = u'Network Genomics'
copyright = u'2021, the Mitogen authors'
exclude_patterns = ['_build', '.venv']
extensions = ['sphinx.ext.autodoc', 'sphinx.ext.intersphinx', 'sphinxcontrib.programoutput', 'domainrefs']

# get rid of version from <title>, it messes with piwik
html_title = 'Mitogen Documentation'

html_show_copyright = False
html_show_sourcelink = False
html_show_sphinx = False
html_sidebars = {'**': ['globaltoc.html', 'github.html']}
html_static_path = ['_static']
html_theme = 'alabaster'
html_theme_options = {
    'font_family': "Georgia, serif",
    'head_font_family': "Georgia, serif",
    'fixed_sidebar': True,
    'show_powered_by': False,
    'pink_2': 'fffafaf',
    'pink_1': '#fff0f0',
}
htmlhelp_basename = 'mitogendoc'
intersphinx_mapping = {'python': ('https://docs.python.org/3', None)}
language = None
master_doc = 'toc'
project = u'Mitogen'
pygments_style = 'sphinx'
release = VERSION
source_suffix = '.rst'
templates_path = ['_templates']
todo_include_todos = False
version = VERSION

domainrefs = {
    'gh:commit': {
        'text': '%s',
        'url': 'https://github.com/mitogen-hq/mitogen/commit/%s',
    },
    'gh:issue': {
        'text': '#%s',
        'url': 'https://github.com/mitogen-hq/mitogen/issues/%s',
    },
    'gh:pull': {
        'text': '#%s',
        'url': 'https://github.com/mitogen-hq/mitogen/pull/%s',
    },
    'gh:ansissue': {
        'text': 'Ansible #%s',
        'url': 'https://github.com/ansible/ansible/issues/%s',
    },
    'gh:anspull': {
        'text': 'Ansible #%s',
        'url': 'https://github.com/ansible/ansible/pull/%s',
    },

    'ans:mod': {
        'text': '%s module',
        'url': 'https://docs.ansible.com/ansible/latest/modules/%s_module.html',
    },
    'ans:conn': {
        'text': '%s connection plug-in',
        'url': 'https://docs.ansible.com/ansible/latest/plugins/connection/%s.html',
    },
    'freebsd:man2': {
        'text': '%s(2)',
        'url': 'https://man.freebsd.org/cgi/man.cgi?query=%s',
    },
    'linux:man1': {
        'text': '%s(1)',
        'url': 'https://man7.org/linux/man-pages/man1/%s.1.html',
    },
    'linux:man2': {
        'text': '%s(2)',
        'url': 'https://man7.org/linux/man-pages/man2/%s.2.html',
    },
    'linux:man3': {
        'text': '%s(3)',
        'url': 'https://man7.org/linux/man-pages/man3/%s.3.html',
    },
    'linux:man7': {
        'text': '%s(7)',
        'url': 'https://man7.org/linux/man-pages/man7/%s.7.html',
    },
}

# > ## Official guidance
# > Query PyPI’s JSON API to determine where to download files from.
# > ## Predictable URLs
# > You can use our conveyor service to fetch this file, which exists for
# > cases where using the API is impractical or impossible.
# > -- https://warehouse.pypa.io/api-reference/integration-guide.html#predictable-urls
rst_epilog = """

.. |mitogen_version| replace:: %(VERSION)s

.. |mitogen_url| replace:: `mitogen-%(VERSION)s.tar.gz <https://files.pythonhosted.org/packages/source/m/mitogen/mitogen-%(VERSION)s.tar.gz>`__

""" % locals()
