"""Managed ExtractionPort: Document AI plus Gemini multimodal over the claim file (lazy SDK).

The heavy SDK import is lazy so the offline profiles import with no ``google-cloud`` present; a
call with nothing reachable raises at the import rather than fabricating an extraction.
"""

from __future__ import annotations

from ...config import Settings
from ...domain.models import ExtractedClaim, RawClaimFile


class CloudExtractionAdapter:
    """Extract structured evidence with Document AI and Gemini multimodal."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def extract(self, claim_file: RawClaimFile) -> ExtractedClaim:
        from google.cloud import documentai_v1  # noqa: F401 - lazy; absent offline

        raise NotImplementedError(
            "managed extraction is deploy-time; configure the Document AI processor and Gemini"
        )
