"""Category templates and their seeds."""

from equivalence_core.templates.loader import (
    GENERIC_CODE,
    definition_from_json,
    load_seed_templates,
    suggest_category,
)
from equivalence_core.templates.model import (
    AttributeDefinition,
    ComparisonRule,
    Criticality,
    Labels,
    ResolvedAttribute,
    RuleSettings,
    TemplateAttribute,
    TemplateDefinition,
    TemplateError,
    ValueType,
)

__all__ = [
    "GENERIC_CODE",
    "AttributeDefinition",
    "ComparisonRule",
    "Criticality",
    "Labels",
    "ResolvedAttribute",
    "RuleSettings",
    "TemplateAttribute",
    "TemplateDefinition",
    "TemplateError",
    "ValueType",
    "definition_from_json",
    "load_seed_templates",
    "suggest_category",
]
