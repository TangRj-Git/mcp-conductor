"""JSON Schema builders used by capability recommendations."""

from __future__ import annotations

from typing import Any

from ..models import Capability, CapabilityType
from ..primitives.templates import resource_template_variables


def recommendation_input_schema(capability: Capability) -> dict[str, Any]:
    """Return the argument schema exposed with one recommendation."""
    if capability.capability_type == CapabilityType.PROMPT:
        return prompt_arguments_schema(capability)
    if capability.capability_type == CapabilityType.RESOURCE_TEMPLATE:
        return resource_template_arguments_schema(capability)
    if capability.capability_type == CapabilityType.RESOURCE:
        return {
            "type": "object",
            "properties": {},
            "additionalProperties": False,
        }
    return capability.schema_or_metadata


def prompt_arguments_schema(capability: Capability) -> dict[str, Any]:
    """Build a minimal JSON Schema from MCP prompt argument metadata."""
    properties: dict[str, Any] = {}
    required: list[str] = []
    for argument in capability.schema_or_metadata.get("arguments", []):
        name = _metadata_value(argument, "name")
        if not name:
            continue
        schema: dict[str, Any] = {"type": "string"}
        description = _metadata_value(argument, "description")
        if description:
            schema["description"] = description
        properties[str(name)] = schema
        if _metadata_value(argument, "required", default=False):
            required.append(str(name))
    schema = {
        "type": "object",
        "properties": properties,
        "additionalProperties": False,
    }
    if required:
        schema["required"] = required
    return schema


def resource_template_arguments_schema(capability: Capability) -> dict[str, Any]:
    """Build a strict argument schema from simple {variable} URI templates."""
    variables = resource_template_variables(capability)
    return {
        "type": "object",
        "properties": {
            variable: {"type": "string"}
            for variable in variables
        },
        "required": variables,
        "additionalProperties": False,
    }


def _metadata_value(value: Any, key: str, default: Any = None) -> Any:
    if isinstance(value, dict):
        return value.get(key, default)
    return getattr(value, key, default)
