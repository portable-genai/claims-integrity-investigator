"""On-prem GenerationPort placeholder (fail-fast): structurally satisfies the Protocol."""

from __future__ import annotations

from ...config import Settings
from ...domain.models import LlmRequest, LlmResponse

_MESSAGE = "On-prem GenerationPort placeholder; implement it (domain unchanged)."


class OnPremGenerationAdapter:
    """Placeholder generation adapter for the on-prem profile."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def generate(self, request: LlmRequest) -> LlmResponse:
        raise NotImplementedError(_MESSAGE)
