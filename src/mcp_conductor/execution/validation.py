from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from jsonschema import SchemaError
from jsonschema.exceptions import best_match
from jsonschema.validators import validator_for


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
    if not input_schema:
        return []

    try:
        validator_class = validator_for(input_schema)
        validator_class.check_schema(input_schema)
        validator = validator_class(input_schema)
    except SchemaError as exc:
        return [f"invalid input schema: {exc.message}"]

    errors = sorted(
        validator.iter_errors(arguments),
        key=lambda error: [str(part) for part in error.path],
    )
    if not errors:
        return []

    best_error = best_match(errors)
    path = ".".join(str(part) for part in best_error.path)
    prefix = f"argument {path}: " if path else ""
    return [f"{prefix}{best_error.message}"]
