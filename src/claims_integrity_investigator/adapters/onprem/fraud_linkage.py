"""On-prem FraudLinkagePort placeholder (fail-fast): structurally satisfies the Protocol."""

from __future__ import annotations

from ...config import Settings
from ...domain.models import FraudLinkage

_MESSAGE = "On-prem FraudLinkagePort placeholder; implement it (domain unchanged)."


class OnPremFraudLinkageAdapter:
    """Placeholder fraud-linkage adapter for the on-prem profile."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def linkage(self, subject: str) -> FraudLinkage:
        raise NotImplementedError(_MESSAGE)
