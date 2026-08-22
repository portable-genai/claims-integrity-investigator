"""ClaimsHistoryPort: the claimant's prior-claims record for the velocity rule.

The managed adapter reads the BigQuery claims-history / linkage dataset; the local adapter
serves a deterministic fixture. The port returns raw prior-claim rows only; the claims-velocity
arithmetic lives in the red-flag engine, never here.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from ..domain.models import ClaimsHistory


@runtime_checkable
class ClaimsHistoryPort(Protocol):
    def history(self, subject: str) -> ClaimsHistory:
        """Return the prior-claims record for ``subject`` (raw rows, no computation)."""
        ...
