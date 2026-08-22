"""Managed GenerationPort: Gemini on the Gemini Enterprise Agent Platform (lazy SDK).

The model narrates only. The SDK import is lazy so offline profiles import with no SDK; a call
with nothing reachable raises at the import rather than fabricating a narrative.
"""

from __future__ import annotations

from ...config import Settings
from ...domain.models import LlmRequest, LlmResponse


class CloudGenerationAdapter:
    """Generate the structured narrative with Gemini."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def generate(self, request: LlmRequest) -> LlmResponse:
        from google import genai  # noqa: F401 - lazy; absent offline

        raise NotImplementedError(
            "managed generation is deploy-time; configure the Gemini model and project"
        )
