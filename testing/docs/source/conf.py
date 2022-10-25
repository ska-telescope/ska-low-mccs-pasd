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
sys.path.insert(0, os.path.abspath('../../src'))


# This is an elaborate hack to insert write property into _all_
# mock decorators. It is needed for getting @attribute to build
# in mocked out tango.server
# see https://github.com/sphinx-doc/sphinx/issues/6709
from sphinx.ext.autodoc.mock import _MockObject


def call_mock(self, *args, **kw):
    from types import FunctionType, MethodType

    if args and type(args[0]) in [type, FunctionType, MethodType]:
        # Appears to be a decorator, pass through unchanged
        args[0].write = lambda x: x
        return args[0]
    return self


_MockObject.__call__ = call_mock
_MockObject.__getitem__ = lambda self, key: _MockObject()
_MockObject.__mul__ = lambda self, other: _MockObject()
_MockObject.__sub__ = lambda self, other: _MockObject()
_MockObject.__truediv__ = lambda self, other: _MockObject()
# hack end




# -- Project information -----------------------------------------------------
release_filename = os.path.join(
    "..", "..", "..", "src", "ska_low_mccs", "release.py"
)
version = None
author = None
for line in open(release_filename).readlines():
    line = line.strip()
    if line.startswith(("author", "version")):
        exec(line)

project = 'SKA Low MCCS tests'
release = version
copyright = '2021, SKA MCCS Team'


# -- General configuration ---------------------------------------------------

# Add any Sphinx extension module names here, as strings. They can be
# extensions coming with Sphinx (named 'sphinx.ext.*') or your custom
# ones.
extensions = [
    "sphinx.ext.autodoc",
    "sphinx.ext.intersphinx",
]

# Add any paths that contain templates here, relative to this directory.
templates_path = ['_templates']

# List of patterns, relative to source directory, that match files and
# directories to ignore when looking for source files.
# This pattern also affects html_static_path and html_extra_path.
exclude_patterns = []

autodoc_mock_imports = ["pytest_bdd", "scipy", "ska_low_mccs", "ska_tango_base", "tango"]

autodoc_default_options = {"special-members": "__init__"}

def setup(app):
    """
    Initialise app.
    """
    app.add_css_file("css/custom.css")
    app.add_js_file("js/gitlab.js")


# -- Options for HTML output -------------------------------------------------

# The theme to use for HTML and HTML Help pages.  See the documentation for
# a list of builtin themes.
#
html_theme = 'sphinx_rtd_theme'

# Add any paths that contain custom static files (such as style sheets) here,
# relative to this directory. They are copied after the builtin static files,
# so a file named "default.css" will overwrite the builtin "default.css".
html_static_path = ['_static']


mccs_inventory_path = os.path.join("..", "..", "..", "docs", "build", "html", "objects.inv")
mccs_inventory = mccs_inventory_path if os.path.exists(mccs_inventory_path) else None
print(f"MCCS inventory path is {mccs_inventory_path}.")

intersphinx_mapping = {
    "https://docs.python.org/3/": None,
    "pytango": ("https://pytango.readthedocs.io/en/stable/", None),
    "pytest": ("https://docs.pytest.org/en/stable/", None),
    "ska_low_mccs": (
        "https://developer.skatelescope.org/projects/ska-low-mccs/en/master/",
         mccs_inventory_path
    ),
    "ska-tango-base": (
        "https://developer.skatelescope.org/projects/ska-tango-base/en/latest/",
        None,
    ),
}

nitpick_ignore = [
    ("py:class", "callable"),
    ("py:class", "contextmanager"),  # actually a std type -- impossible to link to?
    ("py:class", "pytest.config.Config"),  # something not right at pytest end
    ("py:class", "pytest_mock.mocker"),  # pytest_mock has no sphinx docs
    ("py:class", "pytest_mock.mocker.Mock"),
    ("py:class", "pytest_mock.module_mocker"),
]
