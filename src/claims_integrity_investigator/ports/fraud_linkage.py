"""FraudLinkagePort: organised-fraud signals for a claimant, from the G-series suite.

The G-series financial-crime suite (AML triage, sanctions, scam interdiction, ATO, SOC fusion)
publishes organised-fraud signals that this port consumes as a DATA FEED. The default binding is
a local fixture adapter: the row's G-series link is a data feed, not build-time coupling, so an
adopter names a live export (BigQuery / an A2A skill) when one exists (a recorded judgement
call). The port returns raw linkage; the red-flag engine turns a match into a scored indicator.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from ..domain.models import FraudLinkage


@runtime_checkable
class FraudLinkagePort(Protocol):
    def linkage(self, subject: str) -> FraudLinkage:
        """Return any organised-fraud linkage for ``subject`` (raw, unscored)."""
        ...
