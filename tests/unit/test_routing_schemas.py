from __future__ import annotations

from types import SimpleNamespace
from typing import Any

from mcp_conductor.models import Capability, CapabilityType, RiskLevel
from mcp_conductor.routing.schemas import recommendation_input_schema


def make_capability(
    capability_type: CapabilityType,
    *,
    name: str = "capability",
    metadata: dict[str, Any] | None = None,
) -> Capability:
    return Capability(
        capability_id=f"learn.{capability_type.value}.{name}",
        capability_type=capability_type,
        upstream_server_id="learn",
        upstream_client_id="learn",
        original_name_or_uri=name,
        description="Test capability",
        schema_or_metadata=metadata or {},
        tags=["learn"],
        risk_level=RiskLevel.READ_ONLY,
        read_only_hint=True,
        enabled=True,
    )


def test_prompt_recommendation_schema_uses_argument_metadata() -> None:
    capability = make_capability(
        CapabilityType.PROMPT,
        name="explain",
        metadata={
            "arguments": [
                {
                    "name": "topic",
                    "description": "Topic to explain",
                    "required": True,
                },
                SimpleNamespace(
                    name="audience",
                    description="Target audience",
                    required=False,
                ),
            ]
        },
    )

    schema = recommendation_input_schema(capability)

    assert schema == {
        "type": "object",
        "properties": {
            "topic": {
                "type": "string",
                "description": "Topic to explain",
            },
            "audience": {
                "type": "string",
                "description": "Target audience",
            },
        },
        "additionalProperties": False,
        "required": ["topic"],
    }


def test_resource_template_recommendation_schema_uses_unique_uri_variables() -> None:
    capability = make_capability(
        CapabilityType.RESOURCE_TEMPLATE,
        name="mcp://concepts/{name}/related/{name}/{section}",
        metadata={"uri_template": "mcp://concepts/{name}/related/{name}/{section}"},
    )

    schema = recommendation_input_schema(capability)

    assert schema == {
        "type": "object",
        "properties": {
            "name": {"type": "string"},
            "section": {"type": "string"},
        },
        "required": ["name", "section"],
        "additionalProperties": False,
    }


def test_resource_recommendation_schema_has_no_arguments() -> None:
    capability = make_capability(
        CapabilityType.RESOURCE,
        name="mcp://docs/intro",
        metadata={"uri": "mcp://docs/intro"},
    )

    schema = recommendation_input_schema(capability)

    assert schema == {
        "type": "object",
        "properties": {},
        "additionalProperties": False,
    }


def test_tool_recommendation_schema_uses_tool_input_schema() -> None:
    input_schema = {
        "type": "object",
        "properties": {"topic": {"type": "string"}},
        "required": ["topic"],
    }
    capability = make_capability(
        CapabilityType.TOOL,
        name="explain_topic",
        metadata=input_schema,
    )

    schema = recommendation_input_schema(capability)

    assert schema == input_schema
