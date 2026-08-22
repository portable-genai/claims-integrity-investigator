"""Local GenerationPort: a deterministic, grounded narrative builder (no model, SDK-free).

The offline stand-in for Gemini. It does NOT invent text: it reads the figures the drafter
already rendered into the request (the fixed recommendation, the indemnity line, the fraud
score) and the clause ids in the retrieved-wording block, and restates them in a short
narrative. That keeps the offline narrative grounded by construction, so the gate can assert
groundedness against a real generation path rather than only the fallback template.
"""

from __future__ import annotations

import json
import re

from ...config import Settings
from ...domain.models import LlmRequest, LlmResponse

_REC_RE = re.compile(r"Recommendation \(fixed\):\s*(\S+)")
_COVER_RE = re.compile(r"claimed\s+([\d,]+\.\d{2}); indemnity\s+([\d,]+\.\d{2})")
_FRAUD_RE = re.compile(r"Fraud score\s+(\d+\.\d+)")
_CLAUSE_RE = re.compile(r"\[([A-Z0-9-]+)\]")


class LocalGenerationAdapter:
    """Restate the engine's figures as a grounded narrative, deterministically."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def generate(self, request: LlmRequest) -> LlmResponse:
        content = "\n".join(message.content for message in request.messages)
        rec = _REC_RE.search(content)
        cover = _COVER_RE.search(content)
        fraud = _FRAUD_RE.search(content)
        clauses = _dedupe(_CLAUSE_RE.findall(content))

        recommendation = rec.group(1) if rec else "review"
        claimed = cover.group(1) if cover else "0.00"
        indemnity = cover.group(2) if cover else "0.00"
        score = fraud.group(1) if fraud else "0.0"

        narrative = (
            f"The deterministic engine recommends {recommendation}. It assesses an indemnity of "
            f"{indemnity} against {claimed} claimed and a fraud score of {score}. The coverage "
            "verdicts and figures above are restated without change, and the claim is escalated "
            "for adjuster and SIU review before any action."
        )
        body = {"narrative": narrative, "used_source_ids": clauses}
        return LlmResponse(text=json.dumps(body), model="local-deterministic")


def _dedupe(values: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for value in values:
        if value not in seen:
            seen.add(value)
            out.append(value)
    return out
