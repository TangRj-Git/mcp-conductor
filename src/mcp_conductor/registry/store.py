from __future__ import annotations

from dataclasses import dataclass, field

from mcp_conductor.models import Capability


@dataclass(slots=True)
class CapabilityRegistry:
    capabilities: dict[str, Capability] = field(default_factory=dict)

    def add(self, capability: Capability) -> None:
        self.capabilities[capability.capability_id] = capability

    def get(self, capability_id: str) -> Capability:
        return self.capabilities[capability_id]

    def list(self) -> list[Capability]:
        return list(self.capabilities.values())
