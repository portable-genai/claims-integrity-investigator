"""On-prem ClaimsHistoryPort placeholder (fail-fast): structurally satisfies the Protocol."""

from __future__ import annotations

from ...config import Settings
from ...domain.models import ClaimsHistory

_MESSAGE = "On-prem ClaimsHistoryPort placeholder; implement it (domain unchanged)."


class OnPremClaimsHistoryAdapter:
    """Placeholder claims-history adapter for the on-prem profile."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def history(self, subject: str) -> ClaimsHistory:
        raise NotImplementedError(_MESSAGE)
