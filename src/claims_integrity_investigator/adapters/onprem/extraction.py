"""On-prem ExtractionPort placeholder (fail-fast): structurally satisfies the Protocol."""

from __future__ import annotations

from ...config import Settings
from ...domain.models import ExtractedClaim, RawClaimFile

_MESSAGE = "On-prem ExtractionPort placeholder; implement it (domain unchanged)."


class OnPremExtractionAdapter:
    """Placeholder extraction adapter for the on-prem profile."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def extract(self, claim_file: RawClaimFile) -> ExtractedClaim:
        raise NotImplementedError(_MESSAGE)
