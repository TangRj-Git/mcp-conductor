from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Any


class CapabilityType(StrEnum):
    TOOL = "tool"
    RESOURCE = "resource"
    RESOURCE_TEMPLATE = "resource_template"
    PROMPT = "prompt"


class RiskLevel(StrEnum):
    READ_ONLY = "read_only"
    MUTATING = "mutating"
    DESTRUCTIVE = "destructive"
    UNKNOWN = "unknown"


@dataclass(slots=True)
class Capability:
    capability_id: str
    capability_type: CapabilityType
    upstream_server_id: str
    upstream_client_id: str
    original_name_or_uri: str
    description: str | None = None
    schema_or_metadata: dict[str, Any] = field(default_factory=dict)
    tags: list[str] = field(default_factory=list)
    risk_level: RiskLevel = RiskLevel.UNKNOWN
    read_only_hint: bool | None = None
    enabled: bool = True


@dataclass(slots=True)
class CapabilityCard:
    capability_id: str
    name: str
    description: str | None
    tags: list[str]
    risk_level: RiskLevel
    read_only_hint: bool | None
    input_summary: str | None = None
    output_summary: str | None = None


@dataclass(slots=True)
class RecommendedCapability:
    capability_id: str
    route_token: str
    reason: str
    confidence: float | None = None
    input_schema: dict[str, Any] = field(default_factory=dict)
    example_arguments: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class Recommendation:
    recommendation_id: str
    expires_at: datetime
    recommended_capabilities: list[RecommendedCapability]


@dataclass(slots=True)
class ResultReference:
    result_id: str
    expires_at: datetime
    session_id: str | None = None


@dataclass(slots=True)
class PendingAction:
    pending_action_id: str
    expires_at: datetime
    capability_id: str
    arguments: dict[str, Any]
    risk_level: RiskLevel


@dataclass(slots=True)
class GatewayError:
    error_code: str
    message: str
    details: dict[str, Any] = field(default_factory=dict)
