"""Versioned Jinja2 prompts that live inside each service's own package."""

from typing import Any

from jinja2 import Environment, PackageLoader, StrictUndefined


def render(package: str, template: str, /, **context: Any) -> str:
    """Render `<package>/prompts/<template>`; a missing variable raises, never renders empty."""
    environment = Environment(
        loader=PackageLoader(package, "prompts"),
        undefined=StrictUndefined,
        autoescape=False,  # plain-text prompts, not HTML
        keep_trailing_newline=True,
        trim_blocks=True,
        lstrip_blocks=True,
    )
    return environment.get_template(template).render(**context)
