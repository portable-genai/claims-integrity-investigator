"""Managed ClaimsHistoryPort: the BigQuery claims-history / linkage dataset (lazy SDK)."""

from __future__ import annotations

from ...config import Settings
from ...domain.models import ClaimsHistory


class CloudClaimsHistoryAdapter:
    """Read a claimant's prior-claims record from BigQuery."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def history(self, subject: str) -> ClaimsHistory:
        from google.cloud import bigquery  # noqa: F401 - lazy; absent offline

        raise NotImplementedError(
            "managed claims-history retrieval is deploy-time; configure the BigQuery dataset"
        )
