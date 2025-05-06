import os
import sys

# Add the package source directory to the Python path
sys.path.insert(0, os.path.abspath('../src'))

# Configuration file for the Sphinx documentation builder.
project = 'U-shaped Laser Package'
copyright = '2024, Simon T. Thomsen, Jeppe H. Surrow'
author = 'Simon T. Thomsen, Jeppe H. Surrow'

# Add any Sphinx extension module names here, as strings
extensions = [
    'sphinx.ext.autodoc',
    'sphinx.ext.napoleon',
    'sphinx.ext.viewcode',
    'sphinx.ext.intersphinx',
]

# Add any paths that contain templates here, relative to this directory.
templates_path = ['_templates']

# List of patterns, relative to source directory, that match files and
# directories to ignore when looking for source files.
exclude_patterns = ['_build', 'Thumbs.db', '.DS_Store']

# The theme to use for HTML and HTML Help pages
html_theme = 'sphinx_rtd_theme'

# Add any paths that contain custom static files (such as style sheets) here,
# relative to this directory. They are copied after the builtin static files,
# so a file named "default.css" will overwrite the builtin "default.css".
html_static_path = ['_static']

# Intersphinx mapping
intersphinx_mapping = {
    'python': ('https://docs.python.org/3', None),
    'numpy': ('https://numpy.org/doc/stable/', None),
    'scipy': ('https://docs.scipy.org/doc/scipy/', None),
    'matplotlib': ('https://matplotlib.org/stable/', None),
}

# Mock imports for autodoc to handle missing dependencies
autodoc_mock_imports = [
    'numpy',
    'pandas',
    'matplotlib',
    'scipy',
    'cycler',
    'zeta_fit',
    'lwa_lib',
    'file_management_lib',
]

# Autodoc settings
autodoc_member_order = 'bysource'
autodoc_typehints = 'description'
autodoc_docstring_signature = True
autodoc_preserve_defaults = True 