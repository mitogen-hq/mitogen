import os
import sys

sys.path.append('..')

def grep_version():
    path = os.path.join(os.path.dirname(__file__), '../mitogen/__init__.py')
    with open(path) as fp:
        for line in fp:
            if line.startswith('__version__'):
                _, _, s = line.partition('=')
                return '.'.join(map(str, eval(s)))


author = u'David Wilson'
copyright = u'2018, David Wilson'
exclude_patterns = ['_build']
extensions = ['sphinx.ext.autodoc', 'sphinx.ext.intersphinx', 'sphinxcontrib.programoutput']
html_show_sourcelink = False
html_show_sphinx = False
html_sidebars = {'**': ['globaltoc.html', 'github.html']}
html_static_path = ['_static']
html_theme = 'alabaster'
html_theme_options = {
    'font_family': "Georgia, serif",
    'head_font_family': "Georgia, serif",
}
htmlhelp_basename = 'mitogendoc'
intersphinx_mapping = {'python': ('https://docs.python.org/2', None)}
language = None
master_doc = 'toc'
project = u'Mitogen'
pygments_style = 'sphinx'
release = grep_version()
source_suffix = '.rst'
templates_path = ['_templates']
todo_include_todos = False
version = grep_version()
