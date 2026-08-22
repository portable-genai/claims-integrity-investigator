"""Managed ClaimFilePort: claim documents from Cloud Storage / the claims store (lazy SDK).

The SDK import is lazy, so the offline profiles import this module with no ``google-cloud``
installed. With nothing reachable the lazy import is the honest refusal: it raises rather than
returning as if the fetch happened.
"""

from __future__ import annotations

from ...config import Settings
from ...domain.models import RawClaimFile


class CloudClaimFileAdapter:
    """Fetch a claim file from the managed claims-document store."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def fetch(self, claim_id: str, *, tenant: str) -> RawClaimFile:
        from google.cloud import storage  # noqa: F401 - lazy; absent offline, the honest refusal

        raise NotImplementedError(
            "managed claim-file retrieval is deploy-time; configure the claims-document bucket"
        )
