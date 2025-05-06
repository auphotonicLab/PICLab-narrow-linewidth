import os
import sys
sys.path.insert(0, os.path.abspath('../U_shaped_laser_package/src'))

project = 'U-shaped Laser Package'
copyright = '2024, Simon T. Thomsen, Jeppe H. Surrow'
author = 'Simon T. Thomsen, Jeppe H. Surrow'

extensions = [
    'sphinx.ext.autodoc',
    'sphinx.ext.napoleon',
    'sphinx.ext.viewcode',
    'sphinx.ext.intersphinx',
]

templates_path = ['_templates']
exclude_patterns = ['_build', 'Thumbs.db', '.DS_Store']

html_theme = 'sphinx_rtd_theme'
html_static_path = ['_static']

intersphinx_mapping = {
    'python': ('https://docs.python.org/3', None),
    'numpy': ('https://numpy.org/doc/stable/', None),
    'scipy': ('https://docs.scipy.org/doc/scipy/', None),
    'matplotlib': ('https://matplotlib.org/stable/', None),
} 