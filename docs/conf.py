import sys
sys.path.append('..')

author = u'David Wilson'
copyright = u'2016, David Wilson'
exclude_patterns = ['_build']
extensions = ['sphinx.ext.autodoc', 'sphinx.ext.intersphinx']
html_show_sourcelink = False
html_show_sphinx = False
html_sidebars = {'**': ['globaltoc.html', 'github.html']}
html_static_path = ['_static']
html_theme = 'alabaster'
htmlhelp_basename = 'econtextdoc'
intersphinx_mapping = {'python': ('https://docs.python.org/2', None)}
language = None
master_doc = 'toc'
project = u'econtext'
pygments_style = 'sphinx'
release = u'master'
source_suffix = '.rst'
templates_path = ['_templates']
todo_include_todos = False
version = u'master'
