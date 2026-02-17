"""Prompt loading utilities for the protocol processor service.

Provides a Jinja2 Environment pre-configured to load templates from
the prompts directory in this package.
"""

from pathlib import Path

from jinja2 import Environment, FileSystemLoader

# Directory containing prompt templates (this package directory)
PROMPTS_DIR = Path(__file__).parent


def get_prompts_env() -> Environment:
    """Return a Jinja2 Environment for the prompts directory.

    Returns:
        Jinja2 Environment with FileSystemLoader pointing to the prompts directory.
    """
    return Environment(
        loader=FileSystemLoader(str(PROMPTS_DIR)),
        autoescape=False,
    )


def render_system_prompt(**kwargs: object) -> str:
    """Render the system prompt template with the given variables.

    Args:
        **kwargs: Variables to pass to the system.jinja2 template.

    Returns:
        Rendered system prompt string.
    """
    env = get_prompts_env()
    template = env.get_template("system.jinja2")
    return template.render(**kwargs)


def render_user_prompt(**kwargs: object) -> str:
    """Render the user prompt template with the given variables.

    Args:
        **kwargs: Variables to pass to the user.jinja2 template.

    Returns:
        Rendered user prompt string.
    """
    env = get_prompts_env()
    template = env.get_template("user.jinja2")
    return template.render(**kwargs)
