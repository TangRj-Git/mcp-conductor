from __future__ import annotations

from mcp_conductor.models import Capability, CapabilityCard


def build_capability_card(capability: Capability) -> CapabilityCard:
    return CapabilityCard(
        capability_id=capability.capability_id,
        name=capability.original_name_or_uri,
        description=capability.description,
        tags=capability.tags,
        risk_level=capability.risk_level,
        read_only_hint=capability.read_only_hint,
    )
