"""The grounded assessment drafter: the LLM's one job, and it produces no figure.

Mirrors the Doc6 grounded skeleton (render engine findings and retrieved wording -> structured
generation -> map returned source ids back to Citations -> always a draft). The narrative
RESTATES the deterministic engine's coverage verdicts, indemnity quantum and red flags; it never
originates a number or a verdict. Output is schema-validated and DISCARDED on failure, falling
back to a deterministic template so a disposition never waits on generation. Pure domain code:
it talks to the generation port and stdlib only, no cloud SDK.
"""

from __future__ import annotations

import json
from typing import Any

from .kernel import Citation
from .models import (
    CoverageAssessment,
    LlmMessage,
    LlmRequest,
    LlmResponse,
    Recommendation,
    RedFlagAssessment,
    RetrievedPassage,
    money,
)

_DRAFT_MARKER = "[DRAFT: not a decision. Requires adjuster/SIU review and sign-off.]"

_SYSTEM = (
    "You are an insurance claims-assessment drafter. You write a short, factual narrative that "
    "RESTATES the figures and verdicts you are given. You never invent, recompute or change a "
    "figure, a coverage status or a recommendation. Cite every clause you rely on by its source "
    "id. Return JSON only."
)

_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "narrative": {"type": "string"},
        "used_source_ids": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["narrative"],
}


def _render_coverage(coverage: CoverageAssessment) -> str:
    rows = [
        f"- line {line.line_id} ({line.category}): {line.status.value}, "
        f"indemnity {money(line.indemnity_cents)}, {line.reason}"
        for line in coverage.lines
    ]
    header = (
        f"Totals for policy {coverage.policy_ref}: claimed "
        f"{money(coverage.total_claimed_cents)}; indemnity "
        f"{money(coverage.total_indemnity_cents)}."
    )
    return header + "\n" + "\n".join(rows)


def _render_flags(red_flags: RedFlagAssessment) -> str:
    if not red_flags.flags:
        return f"No fraud indicators raised. Fraud score {red_flags.fraud_score}."
    rows = [f"- {flag.kind.value}: {flag.reason}" for flag in red_flags.flags]
    return f"Fraud score {red_flags.fraud_score}. Indicators:\n" + "\n".join(rows)


def _render_passages(passages: tuple[RetrievedPassage, ...]) -> str:
    if not passages:
        return "(no policy wording was retrieved)"
    return "\n".join(
        f"[{p.citation.source_id}] {p.citation.title}: {p.text.strip()}" for p in passages
    )


def _deterministic_narrative(
    recommendation: Recommendation,
    coverage: CoverageAssessment,
    red_flags: RedFlagAssessment,
) -> str:
    """The fallback narrative when generation is unavailable or fails validation."""
    return (
        f"Recommendation: {recommendation.value}. Indemnity "
        f"{money(coverage.total_indemnity_cents)} of {money(coverage.total_claimed_cents)} "
        f"claimed. Fraud score {red_flags.fraud_score} across "
        f"{len(red_flags.flags)} indicator(s). Every figure is the deterministic engine's; this "
        "assessment requires human review before any action."
    )


def _parse(response: LlmResponse) -> dict[str, Any]:
    text = (response.text or "").strip()
    if not text:
        return {}
    try:
        parsed = json.loads(text)
    except (json.JSONDecodeError, ValueError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _citations_for(used: list[str], passages: tuple[RetrievedPassage, ...]) -> tuple[Citation, ...]:
    by_id = {p.citation.source_id: p.citation for p in passages}
    picked = [by_id[sid] for sid in used if sid in by_id]
    if not picked:
        picked = list(by_id.values())
    seen: set[str] = set()
    out: list[Citation] = []
    for citation in picked:
        if citation.source_id not in seen:
            seen.add(citation.source_id)
            out.append(citation)
    return tuple(out)


class AssessmentDrafter:
    """Draft the cited coverage-and-fraud narrative. The model narrates; it never decides."""

    def __init__(self, generation: Any) -> None:
        self._generation = generation

    def draft(
        self,
        recommendation: Recommendation,
        coverage: CoverageAssessment,
        red_flags: RedFlagAssessment,
        passages: tuple[RetrievedPassage, ...],
    ) -> tuple[str, tuple[Citation, ...]]:
        """Return the drafted narrative and the wording citations it relied on.

        On any generation failure, or a response that fails the schema, the deterministic
        template is used instead: interdiction of a claim never waits on the model.
        """
        fallback = _deterministic_narrative(recommendation, coverage, red_flags)
        wording_cites = _citations_for([], passages)
        user = (
            f"Recommendation (fixed): {recommendation.value}\n\n"
            f"{_render_coverage(coverage)}\n\n{_render_flags(red_flags)}\n\n"
            f"Retrieved policy wording:\n{_render_passages(passages)}\n\n"
            "Write a 3-4 sentence narrative restating the above. Do not change any figure."
        )
        request = LlmRequest(
            messages=(LlmMessage(role="user", content=user),),
            system_instruction=_SYSTEM,
            response_schema=_SCHEMA,
        )
        try:
            response = self._generation.generate(request)
        except Exception:  # noqa: BLE001 - a generation failure must never break the disposition
            return f"{_DRAFT_MARKER}\n\n{fallback}", wording_cites
        parsed = _parse(response)
        narrative = str(parsed.get("narrative") or "").strip()
        if not narrative:
            return f"{_DRAFT_MARKER}\n\n{fallback}", wording_cites
        used = [str(s) for s in parsed.get("used_source_ids") or [] if str(s).strip()]
        return f"{_DRAFT_MARKER}\n\n{narrative}", _citations_for(used, passages)
