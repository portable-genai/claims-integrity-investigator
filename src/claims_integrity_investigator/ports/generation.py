"""GenerationPort: the LLM boundary for drafting the cited narrative, and nothing else.

The managed adapter is Gemini on the Gemini Enterprise Agent Platform; the local adapter is a
deterministic template so the offline gate and the demo produce a stable narrative with no
model. The model's whole job is to restate the deterministic engine's figures and verdicts in
prose; it never originates a coverage status, an indemnity figure or a recommendation. Output is
schema-validated and discarded on failure by the drafter, so a disposition never waits on it.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from ..domain.models import LlmRequest, LlmResponse


@runtime_checkable
class GenerationPort(Protocol):
    def generate(self, request: LlmRequest) -> LlmResponse:
        """Generate the structured narrative for ``request`` using the configured model."""
        ...
