"""The grounded assessment drafter: the LLM's one job, and it produces no figure.

Mirrors the complaints-review grounded skeleton (render engine findings and retrieved wording ->
structured generation -> map returned source ids back to Citations -> always a draft). The narrative
RESTATES the deterministic engine's coverage verdicts, indemnity quantum and red flags; it never
originates a number or a verdict. Output is schema-validated and DISCARDED on failure, falling back
to a deterministic template so a disposition never waits on generation. Pure domain code: it talks
to the generation port and stdlib only, no cloud SDK.

Rule R1: the guardrail screens BOTH directions of the one generation call this drafter makes.
The rendered prompt is screened INPUT, as sent, before it ever reaches the model: it carries
every field the model reads, including the free text other systems stored (a coverage line's
reason, an organised-fraud note quoted into a red flag, the retrieved wording), so one screen of
the whole prompt also sees an injection split across two of them. The narrated ``narrative`` is
screened OUTPUT before it is used or returned. The text each screen hands back is the text used
from then on, exactly as given.

Narration is OPTIONAL by design here: a disposition never waits on the model. So a refusal in
either direction, and a guardrail that raised instead of deciding, withholds the model's text and
falls back to the deterministic template (never a partial model narrative), and the returned
:class:`Draft` says so, so the orchestrator audits it ``Decision.BLOCKED`` before the assessment
record is written. The deterministic figures are the engine's either way.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Any

from ..ports.guardrail import GuardrailPort
from .kernel import Citation, Direction
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

#: Rule R1: what a guardrail block replaces the narrative with, so a reviewer can tell a
#: withheld draft from an ordinary generation failure. The deterministic figures are unaffected
#: either way; only the model's restated prose is discarded.
_BLOCKED_MARKER = (
    "[NARRATIVE WITHHELD: the guardrail blocked this draft. The deterministic figures below "
    "are unaffected and are not the model's.]"
)

_log = logging.getLogger(__name__)

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


@dataclass(frozen=True, slots=True)
class Draft:
    """The drafted narrative, the wording it cites, and whether the guardrail withheld it.

    ``blocked_direction`` and ``blocked_reason`` are set together, only when the guardrail
    refused a leg of the generation call (or could not decide): the orchestrator audits that as
    ``Decision.BLOCKED``. The reason never carries the refused text.
    """

    narrative: str
    citations: tuple[Citation, ...]
    blocked_direction: Direction | None = None
    blocked_reason: str = ""


class AssessmentDrafter:
    """Draft the cited coverage-and-fraud narrative. The model narrates; it never decides."""

    def __init__(self, generation: Any, guardrail: GuardrailPort) -> None:
        self._generation = generation
        self._guardrail = guardrail

    def draft(
        self,
        recommendation: Recommendation,
        coverage: CoverageAssessment,
        red_flags: RedFlagAssessment,
        passages: tuple[RetrievedPassage, ...],
    ) -> Draft:
        """Return the drafted narrative and the wording citations it relied on.

        On any generation failure, a guardrail refusal in either direction (rule R1), a
        guardrail that could not decide, or a response that fails the schema, the deterministic
        template is used instead: interdiction of a claim never waits on the model, and never on
        the guardrail either. A guardrail refusal is reported on the returned :class:`Draft`.
        """
        fallback = (
            f"{_DRAFT_MARKER}\n\n{_deterministic_narrative(recommendation, coverage, red_flags)}"
        )
        wording_cites = _citations_for([], passages)
        user = (
            f"Recommendation (fixed): {recommendation.value}\n\n"
            f"{_render_coverage(coverage)}\n\n{_render_flags(red_flags)}\n\n"
            f"Retrieved policy wording:\n{_render_passages(passages)}\n\n"
            "Write a 3-4 sentence narrative restating the above. Do not change any figure."
        )

        # Rule R1: screen the rendered prompt INPUT, as sent, before it ever reaches the model.
        prompt, refused = self._screen(user, Direction.INPUT)
        if prompt is None:
            return self._withheld(fallback, wording_cites, Direction.INPUT, refused)

        request = LlmRequest(
            messages=(LlmMessage(role="user", content=prompt),),
            system_instruction=_SYSTEM,
            response_schema=_SCHEMA,
            # Narration restates figures the engine already fixed; it computes nothing that is
            # compared, so it samples freely (no temperature sent). The figures stay pinned
            # because the engine, not the model, produces them.
            temperature=None,
        )
        try:
            response = self._generation.generate(request)
        except Exception:  # noqa: BLE001 - a generation failure must never break the disposition
            return Draft(fallback, wording_cites)
        parsed = _parse(response)
        narrative = str(parsed.get("narrative") or "").strip()
        if not narrative:
            return Draft(fallback, wording_cites)

        # Rule R1: screen the narrated OUTPUT before it is used, cited or returned.
        screened, refused = self._screen(narrative, Direction.OUTPUT)
        if screened is None:
            return self._withheld(fallback, wording_cites, Direction.OUTPUT, refused)
        # Exactly as the screen handed it back: a screen that redacted everything has not asked
        # for the original, so an emptied narrative falls back rather than restoring it.
        if not screened.strip():
            return Draft(fallback, wording_cites)

        used = [str(s) for s in parsed.get("used_source_ids") or [] if str(s).strip()]
        return Draft(f"{_DRAFT_MARKER}\n\n{screened.strip()}", _citations_for(used, passages))

    def _screen(self, text: str, direction: Direction) -> tuple[str | None, str]:
        """Screen one leg: the text to use from here on, or ``None`` and why it was refused.

        A guardrail that raised has not said "allowed", so it is a refusal too (fail closed):
        the model's text is withheld, and the reason names the error type, never its message,
        which may quote the screened text.
        """
        try:
            verdict = self._guardrail.screen(text, direction)
        except Exception as exc:  # noqa: BLE001 - an undecided screen withholds, never allows
            return None, f"guardrail unavailable ({type(exc).__name__})"
        if not verdict.allowed or verdict.sanitized_text is None:
            return None, verdict.reason or f"narrative {direction.value} blocked by guardrail"
        return verdict.sanitized_text, ""

    @staticmethod
    def _withheld(
        fallback: str, cites: tuple[Citation, ...], direction: Direction, reason: str
    ) -> Draft:
        _log.warning("guardrail withheld the drafted narrative (%s): %s", direction.value, reason)
        return Draft(
            f"{_BLOCKED_MARKER}\n\n{fallback}",
            cites,
            blocked_direction=direction,
            blocked_reason=reason,
        )
