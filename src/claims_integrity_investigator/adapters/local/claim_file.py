"""Local ClaimFilePort: serve fictional claim files from the in-repo fixtures (SDK-free)."""

from __future__ import annotations

from ...config import Settings
from ...domain.models import RawClaimFile
from ._fixtures import CLAIM_FILES


class LocalClaimFileAdapter:
    """Return a fixture claim file, or an empty one for an unknown id (deterministic)."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def fetch(self, claim_id: str, *, tenant: str) -> RawClaimFile:
        """Return the file only when its data tag matches the verified principal's tenant.

        A mismatch raises ``KeyError``, the same answer an unknown id gets, so the caller cannot
        tell a foreign file from an absent one. An untagged file (empty tenant) matches nobody,
        because the fail-closed reading of "we do not know who owns this" is "not you".

        An unknown id inside the caller's OWN tenant still returns the empty placeholder, which
        is the behaviour the assess-an-unknown-claim path relies on.
        """
        found = CLAIM_FILES.get(claim_id)
        if found is not None:
            if not tenant or found.tenant != tenant:
                raise KeyError(f"no claim file {claim_id!r} for tenant {tenant!r}")
            return found
        if not tenant:
            raise KeyError(f"no claim file {claim_id!r} for tenant {tenant!r}")
        return RawClaimFile(
            claim_id=claim_id,
            subject=f"unknown:{claim_id}",
            policy_ref="",
            documents=(),
            tenant=tenant,
        )
