from __future__ import annotations

from typing import Any

from mcp_conductor.models import Capability, CapabilityType, RiskLevel
from mcp_conductor.primitives.templates import (
    expand_resource_template_uri,
    resource_template_uri,
    resource_template_variables,
)


def make_resource_template(
    *,
    name: str = "mcp://concepts/{name}",
    metadata: dict[str, Any] | None = None,
) -> Capability:
    return Capability(
        capability_id="learn.resource_template",
        capability_type=CapabilityType.RESOURCE_TEMPLATE,
        upstream_server_id="learn",
        upstream_client_id="learn",
        original_name_or_uri=name,
        description="Test resource template",
        schema_or_metadata=metadata or {},
        tags=["learn"],
        risk_level=RiskLevel.READ_ONLY,
        read_only_hint=True,
        enabled=True,
    )


def test_resource_template_uri_prefers_metadata_uri_template() -> None:
    capability = make_resource_template(
        name="mcp://fallback/{name}",
        metadata={"uri_template": "mcp://metadata/{name}"},
    )

    uri = resource_template_uri(capability)

    assert uri == "mcp://metadata/{name}"


def test_resource_template_uri_falls_back_to_original_name() -> None:
    capability = make_resource_template(name="mcp://fallback/{name}")

    uri = resource_template_uri(capability)

    assert uri == "mcp://fallback/{name}"


def test_resource_template_variables_preserves_first_seen_unique_order() -> None:
    capability = make_resource_template(
        name="mcp://concepts/{name}/related/{name}/{section}",
    )

    variables = resource_template_variables(capability)

    assert variables == ["name", "section"]


def test_resource_template_variables_supports_common_uri_template_operators() -> None:
    capability = make_resource_template(
        name="mcp://files/{+path}{?query,limit}{&page}{section:3}{tags*}",
    )

    variables = resource_template_variables(capability)

    assert variables == ["path", "query", "limit", "page", "section", "tags"]


def test_expand_resource_template_uri_percent_encodes_variable_values() -> None:
    capability = make_resource_template(
        name="mcp://concepts/{name}/{section}",
    )

    uri = expand_resource_template_uri(
        capability,
        {"name": "client/server", "section": "space value"},
    )

    assert uri == "mcp://concepts/client%2Fserver/space%20value"


def test_expand_resource_template_uri_preserves_reserved_path_separators() -> None:
    capability = make_resource_template(
        name="mcp://files/{+path}",
    )

    uri = expand_resource_template_uri(
        capability,
        {"path": "docs/MCP intro.md"},
    )

    assert uri == "mcp://files/docs/MCP%20intro.md"


def test_expand_resource_template_uri_adds_form_style_query_parameters() -> None:
    capability = make_resource_template(
        name="mcp://search{?query,limit}{&page}",
    )

    uri = expand_resource_template_uri(
        capability,
        {"query": "MCP resources", "limit": 10, "page": 2},
    )

    assert uri == "mcp://search?query=MCP%20resources&limit=10&page=2"
