"""On-prem PolicyCorpusPort placeholder (fail-fast): the on-prem governed-RAG target."""

from __future__ import annotations

from ...config import Settings
from ...domain.models import RetrievalQuery, RetrievedPassage

_MESSAGE = "On-prem PolicyCorpusPort placeholder; implement it (domain unchanged)."


class OnPremPolicyCorpusAdapter:
    """Placeholder governed-retrieval adapter for the on-prem profile."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def retrieve(self, query: RetrievalQuery) -> list[RetrievedPassage]:
        raise NotImplementedError(_MESSAGE)
