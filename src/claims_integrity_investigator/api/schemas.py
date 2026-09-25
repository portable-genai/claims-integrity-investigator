"""API request/response schemas (Pydantic) mapped to/from the pure-domain models."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel

from ..domain.models import ClaimAssessment


class AssessRequest(BaseModel):
    """Assess one claim by id. The claimant and evidence are fetched server-side, not posted."""

    claim_id: str


class CitationModel(BaseModel):
    source_id: str
    title: str
    snippet: str = ""


class CoverageLineModel(BaseModel):
    line_id: str
    category: str
    claimed: str
    status: str
    indemnity: str
    reason: str


class RedFlagModel(BaseModel):
    kind: str
    uplift: float
    reason: str


class AssessResponse(BaseModel):
    claim_id: str
    subject: str
    policy_ref: str
    recommendation: str
    severity: str
    decision: str
    indemnity: str
    fraud_score: float
    summary: str
    narrative: str
    requires_human_review: bool
    #: Where the escalation WENT (rule R8): the human-review-console review id, or the local queue
    #: reference. Empty exactly when ``review_routing`` is not ``routed``.
    review_ref: str = ""
    #: What happened to the hand-off: routed, failed, off or not_required. ``failed`` means the
    #: result is NOT queued for review, and the console says so.
    review_routing: Literal["routed", "failed", "off", "not_required"] = "not_required"
    coverage: list[CoverageLineModel] = []
    red_flags: list[RedFlagModel] = []
    citations: list[CitationModel] = []

    @classmethod
    def from_domain(
        cls,
        result: ClaimAssessment,
        *,
        review_ref: str = "",
        review_routing: str = "not_required",
    ) -> AssessResponse:
        from ..domain.models import money

        return cls(
            claim_id=result.claim_id,
            subject=result.subject,
            policy_ref=result.policy_ref,
            recommendation=result.recommendation.value,
            severity=result.severity.value,
            decision=result.decision.value,
            indemnity=result.indemnity,
            fraud_score=result.red_flags.fraud_score,
            summary=result.summary,
            narrative=result.narrative,
            requires_human_review=result.requires_human_review,
            review_ref=review_ref,
            review_routing=review_routing,  # type: ignore[arg-type]
            coverage=[
                CoverageLineModel(
                    line_id=line.line_id,
                    category=line.category,
                    claimed=money(line.claimed_cents),
                    status=line.status.value,
                    indemnity=money(line.indemnity_cents),
                    reason=line.reason,
                )
                for line in result.coverage.lines
            ],
            red_flags=[
                RedFlagModel(kind=flag.kind.value, uplift=flag.uplift, reason=flag.reason)
                for flag in result.red_flags.flags
            ],
            citations=[
                CitationModel(source_id=c.source_id, title=c.title, snippet=c.snippet)
                for c in result.citations
            ],
        )


class SiuQueueItem(BaseModel):
    claim_id: str
    subject: str
    recommendation: str
    severity: str


class HealthResponse(BaseModel):
    status: str
    profile: str
    region: str
    #: What the UI's model pill states before any answer: where the runtime sits and which model
    #: the bound generator calls. Derived server-side so the UI never guesses. Once a request is
    #: answered, the pill shows that response's ``X-Answered-By`` instead.
    runtime: str = "local"  # "gcp" | "local"
    generator_model: str = "deterministic-offline-stub"
