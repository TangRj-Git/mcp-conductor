from __future__ import annotations


class ClientPrimitivesAdapter:
    """Adapter for capabilities requested from the external Host/Client."""

    def supports_sampling(self) -> bool:
        return False

    def supports_elicitation(self) -> bool:
        return False

    def supports_roots(self) -> bool:
        return False
