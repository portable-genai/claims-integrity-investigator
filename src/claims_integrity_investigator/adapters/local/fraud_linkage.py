"""Local FraudLinkagePort: fictional G-series organised-fraud signals (the DEFAULT binding).

Per the recorded judgement call, the fixture-backed local adapter is the default binding for the
G-series link until an adopter names a live export: the link is a data feed, not build-time
coupling. It returns a deterministic linkage record per subject, matched only for the fictional
ring member so the SIU-refer path is exercised offline.
"""

from __future__ import annotations

from ...config import Settings
from ...domain.models import FraudLinkage
from ._fixtures import fraud_linkage_for


class LocalFraudLinkageAdapter:
    """Return the fixture organised-fraud linkage for a subject (unmatched when unknown)."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def linkage(self, subject: str) -> FraudLinkage:
        return fraud_linkage_for(subject)
