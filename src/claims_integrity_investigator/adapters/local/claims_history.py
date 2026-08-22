"""Local ClaimsHistoryPort: fictional prior-claims records for the offline profile (SDK-free)."""

from __future__ import annotations

from ...config import Settings
from ...domain.models import ClaimsHistory
from ._fixtures import claims_history_for


class LocalClaimsHistoryAdapter:
    """Return the fixture claims-history record for a subject (empty when unknown)."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def history(self, subject: str) -> ClaimsHistory:
        return claims_history_for(subject)
