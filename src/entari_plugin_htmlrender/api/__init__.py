"""Host-neutral public facade for rendering and preparation."""

from entari_plugin_htmlrender.runtime import RuntimeResolver as RuntimeResolver
from entari_plugin_htmlrender.runtime import RuntimeSource as RuntimeSource
from entari_plugin_htmlrender.runtime import resolve_runtime as resolve_runtime
from entari_plugin_htmlrender.runtime import runtime_context as runtime_context

from .preparation import parse_html as parse_html
from .preparation import prepare_markdown as prepare_markdown
from .preparation import prepare_template as prepare_template
from .preparation import prepare_text as prepare_text
from .render import rasterize_html as rasterize_html
from .render import render_html as render_html
from .render import render_markdown as render_markdown
from .render import render_template as render_template
from .render import render_template_html as render_template_html
from .render import render_text as render_text
from .resources import resolve_resource_url as resolve_resource_url
from .resources import resolve_template_vars as resolve_template_vars

__all__ = [
    "RuntimeResolver",
    "RuntimeSource",
    "parse_html",
    "prepare_markdown",
    "prepare_template",
    "prepare_text",
    "rasterize_html",
    "render_html",
    "render_markdown",
    "render_template",
    "render_template_html",
    "render_text",
    "resolve_resource_url",
    "resolve_runtime",
    "resolve_template_vars",
    "runtime_context",
]
