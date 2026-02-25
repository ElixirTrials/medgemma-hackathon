"""Prompt loading utilities for the protocol processor service.

Provides a Jinja2 Environment pre-configured to load templates from
the prompts directory in this package.
"""

from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader

# Directory containing prompt templates (this package directory)
PROMPTS_DIR = Path(__file__).parent

_env = Environment(loader=FileSystemLoader(str(PROMPTS_DIR)), autoescape=False)


def render_template(template_name: str, **kwargs: Any) -> str:
    """Render a named Jinja2 template with the given variables.

    Args:
        template_name: Name of the template file (e.g. "field_mapping.jinja2").
        **kwargs: Variables to pass to the template.

    Returns:
        Rendered template string.
    """
    template = _env.get_template(template_name)
    return template.render(**kwargs)
