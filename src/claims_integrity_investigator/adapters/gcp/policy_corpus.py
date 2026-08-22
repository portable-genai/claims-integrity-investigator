"""Managed PolicyCorpusPort: the Hrz2 governed-RAG retrieval service (the mandated dependency).

Ins1's row makes Hrz2 a hard dependency, so policy wording is retrieved through the Hrz2
governed-RAG service (its managed backend is Gemini API File Search) rather than a generic file
search reached directly. The Hrz2 endpoint is configuration: UNSET or emptied means the caller
allowlist names nobody, and an unconfigured governed-retrieval boundary REFUSES rather than
falling back to an ungoverned search. That refusal is evaluated before any SDK import, so it is
the same on the offline profiles as in a misconfigured deployment.
"""

from __future__ import annotations

from ...config import Settings
from ...domain.models import RetrievalQuery, RetrievedPassage


class Hrz2PolicyCorpusAdapter:
    """Retrieve governed policy wording from the Hrz2 governed-RAG service."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._endpoint = settings.hrz2_endpoint

    def retrieve(self, query: RetrievalQuery) -> list[RetrievedPassage]:
        if not self._endpoint:
            raise RuntimeError(
                "Hrz2 governed-RAG endpoint is unconfigured (CLAIMSINTEG_HRZ2_URL); governed "
                "policy-wording retrieval refuses rather than falling back to an ungoverned "
                "search"
            )
        import httpx  # noqa: F401 - lazy; the governed call is deploy-time

        raise NotImplementedError(
            "managed Hrz2 governed-RAG retrieval is deploy-time; wire the S2S call to Hrz2"
        )
