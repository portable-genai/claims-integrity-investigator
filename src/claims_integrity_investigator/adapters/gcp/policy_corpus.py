"""Managed PolicyCorpusPort: the Governed-RAG retrieval service (the mandated dependency).

claims-integrity-investigator's row makes enterprise-knowledge-base a hard dependency, so policy
wording is retrieved through the enterprise-knowledge-base governed-RAG service (its managed backend
is Gemini API File Search) rather than a generic file search reached directly. The
enterprise-knowledge-base endpoint is configuration: UNSET or emptied means the caller allowlist
names nobody, and an unconfigured governed-retrieval boundary REFUSES rather than falling back to an
ungoverned search. That refusal is evaluated before any SDK import, so it is the same on the offline
profiles as in a misconfigured deployment.
"""

from __future__ import annotations

from ...config import Settings
from ...domain.models import RetrievalQuery, RetrievedPassage


class Hrz2PolicyCorpusAdapter:
    """Retrieve governed policy wording from the Governed-RAG service."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._endpoint = settings.knowledge_base_endpoint

    def retrieve(self, query: RetrievalQuery) -> list[RetrievedPassage]:
        if not self._endpoint:
            raise RuntimeError(
                "Governed-RAG endpoint is unconfigured (CLAIMSINTEG_KNOWLEDGE_BASE_URL); governed "
                "policy-wording retrieval refuses rather than falling back to an ungoverned "
                "search"
            )
        import httpx  # noqa: F401 - lazy; the governed call is deploy-time

        raise NotImplementedError(
            "managed Governed-RAG retrieval is deploy-time; wire the S2S call to "
            "enterprise-knowledge-base"
        )
