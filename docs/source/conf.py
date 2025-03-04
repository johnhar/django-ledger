# Configuration file for the Sphinx documentation builder.
#
# This file only contains a selection of the most common options. For a full
# list see the documentation:
# https://www.sphinx-doc.org/en/master/usage/configuration.html

# -- Path setup --------------------------------------------------------------

# If extensions (or modules to document with autodoc) are in another directory,
# add these directories to sys.path here. If the directory is relative to the
# documentation root, use os.path.abspath to make it absolute, like shown here.
#
import os
import sys
from pathlib import Path
from shutil import copy

import django

HERE = os.path.abspath(os.path.dirname(__file__))
sys.path.insert(0, HERE)

BASE_DIR = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, BASE_DIR)
BASE_DIR_PATH = Path(BASE_DIR)

# print(f'conf_path: {HERE}, project_path: {BASE_DIR}')

os.environ["DJANGO_SETTINGS_MODULE"] = "dev_env.settings"
django.setup()

# copies the readme into the source docs files.
# file is included in .gitignore
copy(src=BASE_DIR_PATH.joinpath('README.md'), dst=BASE_DIR_PATH.joinpath('docs/source/'))

# sys.path.insert(0, os.path.abspath('.'))


# -- Project information -----------------------------------------------------

project = 'Django Ledger'
copyright = '2025, EDMA Group Inc'
author = 'Miguel Sanda'

# -- General configuration ---------------------------------------------------

# Add any Sphinx extension module names here, as strings. They can be
# extensions coming with Sphinx (named 'sphinx.ext.*') or your custom
# ones.
extensions = [
    'sphinx.ext.autodoc',
    'sphinx.ext.autosummary',
    'sphinx.ext.napoleon',
    'myst_parser'
]

# Add any paths that contain templates here, relative to this directory.
templates_path = ['_templates']

# List of patterns, relative to source directory, that match files and
# directories to ignore when looking for source files.
# This pattern also affects html_static_path and html_extra_path.
exclude_patterns = []

# -- Options for HTML output -------------------------------------------------

# The theme to use for HTML and HTML Help pages.  See the documentation for
# a list of builtin themes.
#
html_theme = 'renku'

# Add any paths that contain custom static files (such as style sheets) here,
# relative to this directory. They are copied after the builtin static files,
# so a file named "default.css" will overwrite the builtin "default.css".
html_static_path = ['assets']

source_suffix = {
    '.rst': 'restructuredtext',
    '.txt': 'markdown',
    '.md': 'markdown',
}
