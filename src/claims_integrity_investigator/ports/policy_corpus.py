"""PolicyCorpusPort: governed policy-wording retrieval through enterprise-knowledge-base (the
mandated dependency).

This is the Governed-RAG ``RetrievalPort`` shape (``retrieve(RetrievalQuery)`` returning cited
passages), NOT a generic file search: claims-integrity-investigator's row makes
enterprise-knowledge-base a hard dependency, so the managed adapter calls the Governed-RAG service
(whose managed backend is Gemini API File Search) rather than reaching a search index directly.
Retrieval grounds the coverage clauses and the drafted narrative; when it returns nothing, the
coverage engine refuses rather than guesses.

Claim-file content stays LOCAL to this repo as transient case evidence and is never ingested
into this corpus (a recorded judgement call): the corpus is the insurer's policy wordings, a
governed knowledge base, not the claimant's documents.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from ..domain.models import RetrievalQuery, RetrievedPassage


@runtime_checkable
class PolicyCorpusPort(Protocol):
    def retrieve(self, query: RetrievalQuery) -> list[RetrievedPassage]:
        """Return ranked policy-wording passages with clause-level citations for ``query``."""
        ...
