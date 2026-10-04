"""Sphinx configuration. Build with:

    uv run sphinx-build -b html docs docs/_build/html
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).parent / "_ext"))

project = "Strategy Lab"
author = "Jonathan Schnitzler"
copyright = "2026, Jonathan Schnitzler"
release = "2.0"

extensions = [
    "myst_parser",
    "sphinx.ext.autodoc",
    "sphinx.ext.napoleon",
    "sphinx.ext.viewcode",
    "sphinx.ext.mathjax",
    "labdocs",
]
myst_enable_extensions = ["dollarmath", "colon_fence", "deflist"]
source_suffix = {".md": "markdown", ".rst": "restructuredtext"}
exclude_patterns = ["_build"]

autodoc_member_order = "bysource"
autodoc_default_options = {"members": True, "show-inheritance": True}
autodoc_typehints = "description"
napoleon_google_docstring = True

html_theme = "furo"
html_title = "Strategy Lab"
html_static_path = []
html_theme_options = {
    "sidebar_hide_name": False,
    "light_css_variables": {"color-brand-primary": "#4f5fd6", "color-brand-content": "#4f5fd6"},
    "dark_css_variables": {"color-brand-primary": "#7c8cff", "color-brand-content": "#7c8cff"},
}
