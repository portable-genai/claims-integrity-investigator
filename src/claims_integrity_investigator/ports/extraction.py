"""ExtractionPort: turn a raw claim file into structured evidence. It decides nothing.

The managed adapter is Document AI plus Gemini multimodal (claim documents and photos); the
local adapter is a deterministic parser over the fixture claim files. Extraction gathers claim
lines, dates and the policy schedule; the coverage and red-flag decisions belong to the engines,
never here. The orchestrator redacts the claim file BEFORE handing it here, because the managed
extractor is a model call.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from ..domain.models import ExtractedClaim, RawClaimFile


@runtime_checkable
class ExtractionPort(Protocol):
    def extract(self, claim_file: RawClaimFile) -> ExtractedClaim:
        """Extract structured evidence from a (already-redacted) raw claim file."""
        ...
