"""Local PolicyCorpusPort: the offline stand-in for the Hrz2 governed-RAG retrieval.

There is no Hrz2 emulator, so the local profile serves policy wording from an in-repo fixture
corpus keyed by policy reference. It returns the same :class:`RetrievedPassage` objects with
clause-level citations the managed Hrz2 adapter would, preserving interface parity. Filtering to
the claim's ``policy_ref`` is deterministic, and an unknown policy returns no passages, which is
exactly what makes the coverage engine's refuse-rather-than-guess path testable offline.
"""

from __future__ import annotations

from ...config import Settings
from ...domain.models import RetrievalQuery, RetrievedPassage
from ._fixtures import POLICY_CORPUS


class LocalPolicyCorpusAdapter:
    """Retrieve policy-wording passages from the in-repo fixture corpus."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def retrieve(self, query: RetrievalQuery) -> list[RetrievedPassage]:
        policy_ref = (query.filters or {}).get("policy_ref", "")
        passages = POLICY_CORPUS.get(policy_ref, ())
        ranked = sorted(passages, key=lambda p: p.score, reverse=True)
        return list(ranked[: max(query.top_k, 1)])
