"""Helpers for working with MCP resource URI templates."""

from __future__ import annotations

import re
from typing import Any
from urllib.parse import quote

from ..models import Capability

_URI_TEMPLATE_EXPRESSION_PATTERN = re.compile(r"\{([^{}]+)\}")
_URI_TEMPLATE_OPERATORS = "+#./;?&"
_RESERVED_SAFE_CHARS = ":/?#[]@!$&'()*+,;="


def resource_template_uri(capability: Capability) -> str:
    """Return the URI template string advertised by a resource template capability."""
    uri_template = capability.schema_or_metadata.get("uri_template")
    if uri_template:
        return str(uri_template)
    return capability.original_name_or_uri


def resource_template_variables(capability: Capability) -> list[str]:
    """Return unique URI template variables in first-seen order."""
    uri_template = resource_template_uri(capability)
    variables: list[str] = []
    for expression in _URI_TEMPLATE_EXPRESSION_PATTERN.findall(uri_template):
        for variable in _expression_variables(expression):
            if variable not in variables:
                variables.append(variable)
    return variables


def expand_resource_template_uri(
    capability: Capability,
    arguments: dict[str, Any],
) -> str:
    """Expand common MCP URI templates with percent-encoded argument values."""
    uri = resource_template_uri(capability)
    return _URI_TEMPLATE_EXPRESSION_PATTERN.sub(
        lambda match: _expand_expression(match.group(1), arguments),
        uri,
    )


def _expand_expression(expression: str, arguments: dict[str, Any]) -> str:
    operator, body = _expression_operator_and_body(expression)
    variables = [_parse_variable_spec(item) for item in body.split(",") if item]

    if operator == "?":
        return _expand_named_parameters("?", variables, arguments)
    if operator == "&":
        return _expand_named_parameters("&", variables, arguments)
    if operator == ";":
        return _expand_named_parameters(";", variables, arguments)

    safe = _RESERVED_SAFE_CHARS if operator in {"+", "#"} else ""
    values = [
        _encode_value(arguments[variable], safe=safe, max_length=max_length)
        for variable, max_length in variables
    ]
    if operator == "#":
        return "#" + ",".join(values)
    if operator == ".":
        return "." + ".".join(values)
    if operator == "/":
        return "/" + "/".join(values)
    return ",".join(values)


def _expand_named_parameters(
    prefix: str,
    variables: list[tuple[str, int | None]],
    arguments: dict[str, Any],
) -> str:
    separator = ";" if prefix == ";" else "&"
    parts = []
    for variable, max_length in variables:
        name = quote(variable, safe="")
        value = _encode_value(arguments[variable], safe="", max_length=max_length)
        parts.append(f"{name}={value}")
    return prefix + separator.join(parts)


def _expression_variables(expression: str) -> list[str]:
    _, body = _expression_operator_and_body(expression)
    return [
        variable
        for variable, _ in (
            _parse_variable_spec(item)
            for item in body.split(",")
            if item
        )
    ]


def _expression_operator_and_body(expression: str) -> tuple[str, str]:
    if expression and expression[0] in _URI_TEMPLATE_OPERATORS:
        return expression[0], expression[1:]
    return "", expression


def _parse_variable_spec(spec: str) -> tuple[str, int | None]:
    normalized = spec.strip()
    if normalized.endswith("*"):
        normalized = normalized[:-1]
    if ":" not in normalized:
        return normalized, None
    variable, max_length = normalized.split(":", 1)
    try:
        return variable, int(max_length)
    except ValueError:
        return variable, None


def _encode_value(value: Any, *, safe: str, max_length: int | None) -> str:
    raw = str(value)
    if max_length is not None:
        raw = raw[:max_length]
    return quote(raw, safe=safe)
