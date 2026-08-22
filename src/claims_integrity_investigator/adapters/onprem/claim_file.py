"""On-prem ClaimFilePort placeholder (fail-fast): structurally satisfies the Protocol."""

from __future__ import annotations

from ...config import Settings
from ...domain.models import RawClaimFile

_MESSAGE = "On-prem ClaimFilePort placeholder; implement it (domain unchanged)."


class OnPremClaimFileAdapter:
    """Placeholder claim-file adapter for the on-prem profile."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def fetch(self, claim_id: str, *, tenant: str) -> RawClaimFile:
        raise NotImplementedError(_MESSAGE)
