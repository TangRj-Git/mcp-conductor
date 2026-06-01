from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(slots=True)
class ToolCallValidationInput:
    recommendation_id: str
    route_token: str
    capability_id: str
    arguments: dict[str, Any]


def validate_tool_call(request: ToolCallValidationInput) -> None:
    if not request.recommendation_id:
        raise ValueError("recommendation_id is required")
    if not request.route_token:
        raise ValueError("route_token is required")
    if not request.capability_id:
        raise ValueError("capability_id is required")
    if not isinstance(request.arguments, dict):
        raise ValueError("arguments must be an object")


def validate_arguments(
        arguments: dict[str, Any],
        input_schema: dict[str, Any],
) -> list[str]:
    errors: list[str] = []
    if input_schema.get("type") == "object" and not isinstance(arguments, dict):
        return ["arguments must be an object"]

    for required_key in input_schema.get("required", []):
        if required_key not in arguments:
            errors.append(f"missing required argument: {required_key}")

    properties = input_schema.get("properties", {})
    for key, value in arguments.items():
        expected = properties.get(key, {}).get("type")
        if expected == "integer" and not isinstance(value, int):
            errors.append(f"argument {key} must be an integer")
        elif expected == "string" and not isinstance(value, str):
            errors.append(f"argument {key} must be a string")
        elif expected == "boolean" and not isinstance(value, bool):
            errors.append(f"argument {key} must be a boolean")

    return errors
