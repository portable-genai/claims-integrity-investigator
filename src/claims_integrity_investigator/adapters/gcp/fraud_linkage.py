"""Managed FraudLinkagePort: organised-fraud signals from the G-series export (lazy SDK).

The G-series link is a data feed; the managed binding reads the exported linkage table from
BigQuery. Lazy import, so the offline profiles import with no SDK and a live-less call refuses.
"""

from __future__ import annotations

from ...config import Settings
from ...domain.models import FraudLinkage


class CloudFraudLinkageAdapter:
    """Read organised-fraud linkage for a subject from the G-series BigQuery export."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def linkage(self, subject: str) -> FraudLinkage:
        from google.cloud import bigquery  # noqa: F401 - lazy; absent offline

        raise NotImplementedError(
            "managed fraud-linkage retrieval is deploy-time; configure the G-series export table"
        )
