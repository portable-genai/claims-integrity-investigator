"""The claim-assessment orchestrator: deterministic disposition, redact-before-model, R8.

The consequential outputs (per-line coverage, the indemnity quantum, the fraud indicators and
the accept / investigate / decline / SIU-refer recommendation) are ALL produced by the pure
engines; the model only drafts the cited narrative that restates them. The order mirrors the
complaints-review service: fetch, REDACT before any model call, extract, retrieve governed wording,
run the coverage and red-flag engines, recommend, draft, then redact again before the audit
write. Every assessment is consequential, so ``requires_human_review`` is always True and the
surfaces route it to human-review-console (rule R8).

Rule R1: the guardrail screens both directions of BOTH model calls an assessment makes.

- Extraction (Document AI plus Gemini multimodal under ``gcp``) reads the claim file, the most
  caller-controlled text in the system. The redacted file is screened INPUT, whole, as the
  extractor reads it (the subject and every document, so an injection split across two
  documents is seen), and the extracted evidence's free text is screened OUTPUT before any
  engine reasons over it. Extraction is not optional, so a refusal, or a guardrail that could
  not decide, is audited ``Decision.BLOCKED`` with no severity (nothing was scored) and raises
  :class:`~.errors.GuardrailBlockedError` (or the guardrail's own error): never a partial
  assessment.
- Narration (``domain/drafting.py``) is optional by design: a refused narrative falls back to
  the deterministic template, and is still audited ``Decision.BLOCKED`` here, with the severity
  that was scored, before the assessment's own record.
"""

from __future__ import annotations

from dataclasses import replace
from typing import Any

from pii_kit import redact

from ..ports.audit import AuditSinkPort
from ..ports.guardrail import GuardrailPort
from ..ports.observability import ObservabilityTracerPort
from .coverage_engine import CoverageEngine
from .drafting import AssessmentDrafter
from .errors import GuardrailBlockedError
from .kernel import AuditEvent, Citation, Decision, Direction, Severity, utcnow
from .models import (
    ClaimAssessment,
    ClaimsHistory,
    CoverageAssessment,
    ExtractedClaim,
    FraudLinkage,
    RawClaimFile,
    RawDocument,
    Recommendation,
    RedFlagAssessment,
    RetrievalQuery,
    RetrievedPassage,
    money,
)
from .pii import PII_PATTERNS
from .policy import AssessmentPolicy
from .red_flags import RedFlagEngine

#: One span per assessed claim. Structural attributes only: see
#: :meth:`ClaimAssessmentService.assess`.
_ASSESS_SPAN = "claims.assess"

#: Recommendation -> audit severity band. The band drives review priority and dual control; it
#: is not the disposition, which is the ``Recommendation`` itself.
_SEVERITY_BY_RECOMMENDATION: dict[Recommendation, Severity] = {
    Recommendation.SIU_REFER: Severity.CRITICAL,
    Recommendation.INVESTIGATE: Severity.HIGH,
    Recommendation.DECLINE: Severity.MEDIUM,
    Recommendation.ACCEPT: Severity.LOW,
}


def recommend(
    coverage: CoverageAssessment,
    red_flags: RedFlagAssessment,
    policy: AssessmentPolicy,
) -> Recommendation:
    """The pure disposition rule. Fraud outranks coverage; no cover declines; else accept."""
    organised = any(flag.kind.value == "organised_fraud_link" for flag in red_flags.flags)
    if organised or red_flags.fraud_score >= policy.siu_refer_score:
        return Recommendation.SIU_REFER
    if red_flags.fraud_score >= policy.investigate_score:
        return Recommendation.INVESTIGATE
    if coverage.total_indemnity_cents <= 0:
        return Recommendation.DECLINE
    return Recommendation.ACCEPT


class ClaimAssessmentService:
    """Assess one claim end to end, record an already-redacted audit event, escalate to a human."""

    def __init__(
        self,
        *,
        claim_file: Any,
        extraction: Any,
        policy_corpus: Any,
        claims_history: Any,
        fraud_linkage: Any,
        generation: Any,
        guardrail: GuardrailPort,
        audit: AuditSinkPort,
        tracer: ObservabilityTracerPort,
        policy: AssessmentPolicy,
    ) -> None:
        self._claim_file = claim_file
        self._extraction = extraction
        self._policy_corpus = policy_corpus
        self._claims_history = claims_history
        self._fraud_linkage = fraud_linkage
        self._audit = audit
        self._tracer = tracer
        self._policy = policy
        self._guardrail = guardrail
        self._coverage_engine = CoverageEngine()
        self._red_flag_engine = RedFlagEngine(policy=policy)
        self._drafter = AssessmentDrafter(generation, guardrail)

    def assess(self, claim_id: str, *, actor: str, tenant: str) -> ClaimAssessment:
        """Assess ``tenant``'s claim ``claim_id`` end to end, inside one span.

        ``tenant`` is the VERIFIED principal's, never a value from a request body, and it is
        required rather than defaulted: a claim id is a name and not an entitlement, and the port
        below refuses a file whose data tag does not match. It raises ``KeyError`` for a foreign
        file exactly as it does for an absent one, so the surfaces answer 404 either way.

        The span's attributes are STRUCTURAL only: the action and the actor, never the claim
        id, the claimant, the claim file text or the drafted narrative. A trace backend is not
        the WORM audit trail: it has no redaction stage, a wider read audience and no retention
        rule written against a regulator's requirement, so anything content-shaped that reaches
        a span has left the boundary the redact-before-model and redact-before-audit calls
        exist to hold, and left it silently.
        """
        with self._tracer.span(_ASSESS_SPAN, action="assess_claim", actor=actor):
            raw = self._claim_file.fetch(claim_id, tenant=tenant)
            # Redact BEFORE the extraction model ever sees the file (P-04): the multimodal
            # extractor is a model call, so claimant identifiers are masked on the way in, not
            # just on the way to the audit sink. The local extractor is deterministic, but the
            # ORDER is the same on every profile so the guarantee does not depend on which
            # adapter is bound.
            redacted_raw = _redact_raw(raw)
            # Rule R1: the extractor is a model call over caller-controlled text, so the file it
            # reads is screened INPUT first, and what it extracted is screened OUTPUT before any
            # engine, prompt or record uses it.
            self._screen_extraction(
                _claim_file_text(redacted_raw), Direction.INPUT, claim_id=claim_id, actor=actor
            )
            extracted = self._extraction.extract(redacted_raw)
            self._screen_extraction(
                _extracted_text(extracted), Direction.OUTPUT, claim_id=claim_id, actor=actor
            )

            passages = self._retrieve_wording(extracted)
            coverage = self._coverage_engine.assess(extracted, passages)
            # These two ports return STORED rows from OTHER systems, fetched after extraction, so
            # `_redact_raw` never saw them. The organised-fraud note in particular is free text
            # somebody typed, and it is quoted verbatim into a red flag's reason (which goes into
            # the drafting prompt) and into a citation snippet (which goes into the WORM record).
            # Masked HERE, as they cross out of their edge, so the engine, the model, the record
            # and the console are covered once instead of four times.
            history = _redact_history(self._claims_history.history(extracted.subject))
            linkage = _redact_linkage(self._fraud_linkage.linkage(extracted.subject))
            red_flags = self._red_flag_engine.evaluate(extracted, history, linkage)

            recommendation = recommend(coverage, red_flags, self._policy)
            severity = _SEVERITY_BY_RECOMMENDATION[recommendation]
            draft = self._drafter.draft(recommendation, coverage, red_flags, passages)
            narrative, wording_cites = draft.narrative, draft.citations
            if draft.blocked_direction is not None:
                # Narration is optional, so the assessment goes on with the deterministic
                # template; the refusal is still a security event the WORM trail must hold.
                self._audit_blocked(
                    actor,
                    f"{claim_id}: narrative blocked",
                    draft.blocked_direction,
                    draft.blocked_reason,
                    severity=severity,
                )

            summary = (
                f"{claim_id}: {recommendation.value}; indemnity "
                f"{money(coverage.total_indemnity_cents)} of "
                f"{money(coverage.total_claimed_cents)} claimed; fraud "
                f"{red_flags.fraud_score}"
            )
            citations = _redacted_citations(_collect_citations(coverage, red_flags, wording_cites))
            assessment = ClaimAssessment(
                claim_id=claim_id,
                subject=extracted.subject,
                policy_ref=extracted.policy_ref,
                recommendation=recommendation,
                severity=severity,
                decision=Decision.ESCALATED,
                coverage=coverage,
                red_flags=red_flags,
                indemnity_cents=coverage.total_indemnity_cents,
                summary=summary,
                narrative=narrative,
                requires_human_review=True,
                citations=citations,
            )
            self._record(assessment, actor=actor)
            return assessment

    def _screen_extraction(
        self, text: str, direction: Direction, *, claim_id: str, actor: str
    ) -> None:
        """Screen one leg of the extraction call; refuse the assessment if it is not allowed.

        Allowed means allowed with the text UNCHANGED. The screen sees the claim file (or the
        extracted evidence) as one joined text, and a rewrite of that text cannot be mapped back
        onto the documents or the structured fields it came from, so a screen that rewrote it
        refuses too rather than letting the unscreened original through. A block, and a
        guardrail that raised instead of deciding, both fail closed after an audited BLOCKED
        record with no severity, because nothing has been scored.
        """
        what = f"{claim_id}: extraction blocked"
        try:
            verdict = self._guardrail.screen(text, direction)
        except Exception as exc:
            reason = f"guardrail unavailable ({type(exc).__name__})"
            try:
                self._audit_blocked(actor, what, direction, reason, severity=None)
            except Exception as audit_exc:
                exc.add_note(f"the BLOCKED audit record could not be written: {audit_exc!r}")
            raise
        if not verdict.allowed or verdict.sanitized_text is None:
            reason = verdict.reason or f"extraction {direction.value} blocked by guardrail"
        elif verdict.sanitized_text != text:
            reason = "the guardrail rewrote the claim file, which cannot be mapped back onto it"
        else:
            return
        self._audit_blocked(actor, what, direction, reason, severity=None)
        raise GuardrailBlockedError(reason)

    def _audit_blocked(
        self,
        actor: str,
        what: str,
        direction: Direction,
        reason: str,
        *,
        severity: Severity | None,
    ) -> None:
        """Audit a guardrail refusal (rule R1/R2). Never carries the refused text.

        Only that a refusal happened, to which call, in which direction and why. ``severity`` is
        the band already scored, or ``None`` when the refusal came before any scoring.
        """
        self._audit.record(
            AuditEvent(
                action="assess_claim",
                actor=actor,
                decision=Decision.BLOCKED,
                severity=severity,
                redacted_summary=redact(f"{what} ({direction.value}): {reason}", PII_PATTERNS),
                citations=(),
                timestamp=utcnow(),
            )
        )

    def _retrieve_wording(self, extracted: ExtractedClaim) -> tuple[RetrievedPassage, ...]:
        categories = " ".join(sorted({line.category for line in extracted.lines}))
        query = RetrievalQuery(
            text=f"policy {extracted.policy_ref} coverage exclusions {categories}".strip(),
            filters={"policy_ref": extracted.policy_ref},
        )
        passages = self._policy_corpus.retrieve(query)
        return tuple(passages)

    def _record(self, assessment: ClaimAssessment, *, actor: str) -> None:
        """Write the WORM row. Citations are masked HERE too, not only where they were built.

        The assessment reaching this method already carries masked citations; masking again is a
        no-op on that path and is not redundant, because this is the last line before the record
        becomes immutable and every future caller of `_record` inherits the guarantee instead of
        having to remember it.
        """
        redacted = redact(f"{assessment.summary} :: {assessment.narrative}", PII_PATTERNS)
        self._audit.record(
            AuditEvent(
                action="assess_claim",
                actor=actor,
                decision=assessment.decision,
                severity=assessment.severity,
                redacted_summary=redacted,
                citations=_redacted_citations(assessment.citations),
                timestamp=utcnow(),
            )
        )


def build_assessment_service(container: Any) -> ClaimAssessmentService:
    """Wire the orchestrator from a DI container (the one composition point for every surface).

    Takes the ports off the container and the adopter-owned policy off its settings, so the API,
    the CLI, the agent tools and the eval all construct the service the same way rather than each
    repeating the six-port constructor.
    """
    return ClaimAssessmentService(
        claim_file=container.claim_file,
        extraction=container.extraction,
        policy_corpus=container.policy_corpus,
        claims_history=container.claims_history,
        fraud_linkage=container.fraud_linkage,
        generation=container.generation,
        guardrail=container.guardrail,
        audit=container.audit,
        tracer=container.tracer,
        policy=container.settings.policy,
    )


def _claim_file_text(raw: RawClaimFile) -> str:
    """The claim file as the extractor reads it, joined: the subject, then every document."""
    return "\n\n".join([raw.subject, *(doc.text for doc in raw.documents)])


def _extracted_text(extracted: ExtractedClaim) -> str:
    """Every free-text field extraction produced, joined, for the OUTPUT screen."""
    parts = [extracted.subject, extracted.policy_ref]
    parts.extend(
        f"{line.category} {line.description} {line.invoice_no}" for line in extracted.lines
    )
    parts.extend(f"{item.category} {item.exclusion_clause}" for item in extracted.schedule)
    parts.append(extracted.adjuster_notes)
    return "\n".join(parts)


def _redact_raw(raw: RawClaimFile) -> RawClaimFile:
    """Mask claimant identifiers in the whole claim file before the extraction model reads it.

    The SUBJECT is masked as well as the documents. Masking only the documents left the one field
    an insurer most often keys by name and national id untouched, and the extractor copies it
    straight onto ``ExtractedClaim``, from where it reaches the model's input object, the
    claims-history citation locator and the returned assessment.
    """
    documents = tuple(
        RawDocument(doc_ref=doc.doc_ref, kind=doc.kind, text=redact(doc.text, PII_PATTERNS))
        for doc in raw.documents
    )
    return replace(raw, subject=redact(raw.subject, PII_PATTERNS), documents=documents)


def _redact_history(history: ClaimsHistory) -> ClaimsHistory:
    """Mask the subject on a prior-claims record read from the claims warehouse."""
    return replace(history, subject=redact(history.subject, PII_PATTERNS))


def _redact_linkage(linkage: FraudLinkage) -> FraudLinkage:
    """Mask the free-text note on an organised-fraud record read from the G-series feed."""
    return replace(
        linkage,
        subject=redact(linkage.subject, PII_PATTERNS),
        ring_ref=redact(linkage.ring_ref, PII_PATTERNS),
        detail=redact(linkage.detail, PII_PATTERNS),
    )


def _redacted_citations(citations: tuple[Citation, ...]) -> tuple[Citation, ...]:
    """Mask every field of every citation. The WORM boundary, held by construction.

    Citations are assembled from three sources and only one of them has been through
    ``_redact_raw``: the coverage lines come from the redacted extraction, but the prior-claims
    and organised-fraud citations quote STORED records fetched from other systems AFTER
    extraction, and a linkage note is free text somebody typed. Masking here rather than at each
    producer means a fourth source added later is covered the day it is added, and a snippet that
    carries no identifier is masked to itself.
    """
    return tuple(
        Citation(
            source_id=redact(c.source_id, PII_PATTERNS),
            title=redact(c.title, PII_PATTERNS),
            snippet=redact(c.snippet, PII_PATTERNS),
        )
        for c in citations
    )


def _collect_citations(
    coverage: CoverageAssessment,
    red_flags: RedFlagAssessment,
    wording_cites: tuple[Citation, ...],
) -> tuple[Citation, ...]:
    """Gather every distinct citation the assessment stands on, in a stable order."""
    seen: set[tuple[str, str]] = set()
    out: list[Citation] = []
    for group in (
        [c for line in coverage.lines for c in line.citations],
        [c for flag in red_flags.flags for c in flag.citations],
        list(wording_cites),
    ):
        for citation in group:
            key = (citation.source_id, citation.snippet)
            if key not in seen:
                seen.add(key)
                out.append(citation)
    return tuple(out)
