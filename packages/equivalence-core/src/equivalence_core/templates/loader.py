"""Builds template definitions from the packaged YAML seeds or from the hub's JSON."""

from collections.abc import Mapping
from importlib import resources
from typing import Any

import yaml
from pydantic import BaseModel, ConfigDict

from equivalence_core.templates.model import (
    AttributeDefinition,
    ResolvedAttribute,
    TemplateAttribute,
    TemplateDefinition,
    TemplateError,
)

GENERIC_CODE = "generic_consumable"
_ATTRIBUTES_FILE = "attributes.yaml"


class _SeedTemplate(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    code: str
    parent: str | None = None
    keywords: tuple[str, ...] = ()
    limited_template: bool = False
    attributes: tuple[TemplateAttribute, ...]


def load_seed_templates() -> dict[str, TemplateDefinition]:
    """The starting templates, with the parent's attributes merged into each child."""
    seed_dir = resources.files("equivalence_core.templates") / "seed"
    definitions = {
        entry["key"]: AttributeDefinition.model_validate(entry)
        for entry in _read_yaml(seed_dir / _ATTRIBUTES_FILE)["attributes"]
    }
    seeds = {
        seed.code: seed
        for seed in (
            _SeedTemplate.model_validate(_read_yaml(path))
            for path in seed_dir.iterdir()
            if path.name.endswith(".yaml") and path.name != _ATTRIBUTES_FILE
        )
    }
    return {code: _resolve(seeds[code], seeds, definitions) for code in sorted(seeds)}


def definition_from_json(data: Mapping[str, Any]) -> TemplateDefinition:
    """A definition as served by the hub; validated by the same model as the seeds."""
    return TemplateDefinition.model_validate(data)


def suggest_category(name: str, templates: Mapping[str, TemplateDefinition]) -> str:
    """The template whose keyword appears first in the name; German names lead with the noun."""
    folded = name.casefold()
    positions = [
        (index, code)
        for code, template in templates.items()
        for keyword in template.keywords
        if (index := folded.find(keyword.casefold())) >= 0
    ]
    return min(positions)[1] if positions else GENERIC_CODE


def _resolve(
    seed: _SeedTemplate,
    seeds: Mapping[str, _SeedTemplate],
    definitions: Mapping[str, AttributeDefinition],
) -> TemplateDefinition:
    entries = [*_inherited(seed, seeds), *seed.attributes]
    try:
        attributes = tuple(
            ResolvedAttribute(
                **definitions[entry.key].model_dump(), **entry.model_dump(exclude={"key"})
            )
            for entry in entries
        )
    except KeyError as exc:
        raise TemplateError(f"{seed.code}: attribute {exc.args[0]!r} is not defined") from exc
    return TemplateDefinition(
        code=seed.code,
        keywords=seed.keywords,
        limited_template=seed.limited_template,
        attributes=attributes,
    )


def _inherited(seed: _SeedTemplate, seeds: Mapping[str, _SeedTemplate]) -> list[TemplateAttribute]:
    if seed.parent is None:
        return []
    if seed.parent not in seeds:
        raise TemplateError(f"{seed.code}: unknown parent {seed.parent!r}")
    parent = seeds[seed.parent]
    return [*_inherited(parent, seeds), *parent.attributes]


def _read_yaml(path: resources.abc.Traversable) -> dict[str, Any]:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise TemplateError(f"{path.name}: expected a mapping at the top level")
    return data
