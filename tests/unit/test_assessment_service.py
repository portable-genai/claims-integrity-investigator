"""The orchestrator: redact-before-model ordering, always-human disposition, grounded narrative.

Slice 1's ordering proof (the extraction model never sees a raw identifier), slice 5's
review-safety proof (all four dispositions set ``requires_human_review`` and route), and the
groundedness proof (every figure in the drafted narrative is the engine's) live here.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import asdict, replace
from typing import Any

from claims_integrity_investigator.adapters._review_payload import result_to_review
from claims_integrity_investigator.adapters.local import _fixtures as fixtures
from claims_integrity_investigator.adapters.local._fixtures import FIXTURE_TENANT
from claims_integrity_investigator.adapters.local.extraction import LocalExtractionAdapter
from claims_integrity_investigator.config import Settings, build_container
from claims_integrity_investigator.domain.assessment_service import (
    ClaimAssessmentService,
    build_assessment_service,
)
from claims_integrity_investigator.domain.models import (
    FraudLinkage,
    LlmResponse,
    RawClaimFile,
    money,
)

from tests.fixtures import sample_cases

_SETTINGS = Settings(profile="local", audit_path=":memory:")


def _service() -> ClaimAssessmentService:
    return build_assessment_service(build_container(_SETTINGS))


class _SpyExtraction:
    """Wraps the real extractor and records what it was handed.

    ``files`` keeps the WHOLE claim file, not only ``seen``'s document bodies. Recording just the
    bodies is how an unmasked ``subject`` on the same object stayed invisible to a test whose
    name says the model sees no raw identifier.
    """

    def __init__(self, settings: Settings) -> None:
        self._inner = LocalExtractionAdapter(settings)
        self.seen: list[str] = []
        self.files: list[RawClaimFile] = []

    def extract(self, claim_file: RawClaimFile) -> Any:
        self.files.append(claim_file)
        self.seen.extend(doc.text for doc in claim_file.documents)
        return self._inner.extract(claim_file)


@contextmanager
def _planted_fixtures() -> Iterator[None]:
    """Plant an id in the claim SUBJECT and an address in the G-series linkage note.

    Both are STORED rows the service reads, not text a caller posted, so they exercise the two
    paths `_redact_raw` could not reach. Restored afterwards: the fixture dicts are module-level.
    """
    claim_id = sample_cases.RING_CLAIM
    original_file = fixtures.CLAIM_FILES[claim_id]
    original_linkage = dict(fixtures.FRAUD_LINKAGE)
    subject = f"{original_file.subject} NRIC {sample_cases.PLANTED_NRIC}"
    fixtures.CLAIM_FILES[claim_id] = replace(original_file, subject=subject)
    fixtures.FRAUD_LINKAGE[subject] = FraudLinkage(
        subject=subject,
        matched=True,
        ring_ref="RING-DELTA-7",
        detail=(
            "clinic and repairer both flagged in a staged-collision ring; "
            f"refer to {sample_cases.PLANTED_EMAIL}"
        ),
    )
    try:
        yield
    finally:
        fixtures.CLAIM_FILES[claim_id] = original_file
        fixtures.FRAUD_LINKAGE.clear()
        fixtures.FRAUD_LINKAGE.update(original_linkage)


def test_redaction_happens_before_the_extraction_model_sees_the_file() -> None:
    """Slice 1: the claim file is redacted BEFORE extraction, on every profile."""
    container = build_container(_SETTINGS)
    spy = _SpyExtraction(_SETTINGS)
    service = ClaimAssessmentService(
        claim_file=container.claim_file,
        extraction=spy,
        policy_corpus=container.policy_corpus,
        claims_history=container.claims_history,
        fraud_linkage=container.fraud_linkage,
        generation=container.generation,
        audit=container.audit,
        tracer=container.tracer,
        policy=_SETTINGS.policy,
    )
    service.assess(sample_cases.PLANTED_NRIC_CLAIM, actor="tester", tenant=FIXTURE_TENANT)
    assert spy.seen, "the extractor was never called"
    joined = "\n".join(spy.seen)
    assert sample_cases.PLANTED_NRIC not in joined, "a raw NRIC reached the extraction model"
    assert "REDACTED" in joined, "the redaction step did not run before extraction"


def test_every_disposition_requires_human_review_and_is_consequential() -> None:
    """Slice 5 review-safety: all four outcomes always escalate (never auto-execute)."""
    service = _service()
    expected = {
        sample_cases.ACCEPT_CLAIM: "accept",
        sample_cases.DECLINE_CLAIM: "decline",
        sample_cases.INVESTIGATE_CLAIM: "investigate",
        sample_cases.SIU_CLAIM: "siu_refer",
    }
    for claim_id, disposition in expected.items():
        result = service.assess(claim_id, actor="tester", tenant=FIXTURE_TENANT)
        assert result.recommendation.value == disposition, claim_id
        assert result.requires_human_review is True, claim_id
        assert result.decision.value == "escalated", claim_id


def test_the_narrative_only_restates_engine_figures() -> None:
    """Groundedness: the indemnity and fraud score in the narrative are the engine's own."""
    result = _service().assess(sample_cases.SIU_CLAIM, actor="tester", tenant=FIXTURE_TENANT)
    assert money(result.indemnity_cents) in result.narrative
    assert str(result.red_flags.fraud_score) in result.narrative
    # The draft marker makes it unmistakable the system has not decided.
    assert "DRAFT" in result.narrative


def test_the_narrative_falls_back_when_generation_fails() -> None:
    """Slice 5: a generation failure must not break the disposition; the fallback is used."""
    container = build_container(_SETTINGS)

    class _Boom:
        def generate(self, request: Any) -> Any:
            raise RuntimeError("model unavailable")

    service = ClaimAssessmentService(
        claim_file=container.claim_file,
        extraction=container.extraction,
        policy_corpus=container.policy_corpus,
        claims_history=container.claims_history,
        fraud_linkage=container.fraud_linkage,
        generation=_Boom(),
        audit=container.audit,
        tracer=container.tracer,
        policy=_SETTINGS.policy,
    )
    result = service.assess(sample_cases.ACCEPT_CLAIM, actor="tester", tenant=FIXTURE_TENANT)
    assert result.recommendation.value == "accept"
    assert money(result.indemnity_cents) in result.narrative


def test_no_planted_identifier_reaches_the_model_the_worm_record_or_the_console() -> None:
    """The three sinks, one test: what the model reads, what the WORM record keeps, what leaves.

    Two planted identifiers on two different routes, because the boundary held on one and not the
    other. `_redact_raw` masked the claim file's DOCUMENTS, so the FNOL free text was safe; it
    did not mask the claim file's SUBJECT, which the extractor copies straight through, and it
    could not touch the organised-fraud linkage, which is a STORED record from another system
    fetched after extraction and quoted verbatim into a citation snippet.

    The audit scan reads the citations as well as the summary. Scanning the summary alone is what
    let the linkage note through: the summary was masked and the citation beside it was not.
    """
    container = build_container(_SETTINGS)
    with _planted_fixtures():
        spy = _SpyExtraction(_SETTINGS)
        service = ClaimAssessmentService(
            claim_file=container.claim_file,
            extraction=spy,
            policy_corpus=container.policy_corpus,
            claims_history=container.claims_history,
            fraud_linkage=container.fraud_linkage,
            generation=container.generation,
            audit=container.audit,
            tracer=container.tracer,
            policy=_SETTINGS.policy,
        )
        result = service.assess(
            sample_cases.RING_CLAIM, actor=sample_cases.ACTOR, tenant=FIXTURE_TENANT
        )
    planted = (sample_cases.PLANTED_NRIC, sample_cases.PLANTED_EMAIL)

    # 1. The model. The WHOLE claim file it was handed, not only the document bodies.
    assert spy.files, "the extractor was never called"
    read_by_model = json.dumps([asdict(f) for f in spy.files], default=str)
    for token in planted:
        assert token not in read_by_model, f"{token} reached the extraction model"

    # 2. The WORM record. Content fields only: `actor` is the verified principal and is an
    #    address by design, so scanning it would make this unfailable in the wrong direction.
    rows = [dict(row) for row in container.audit.log.read_all()]
    assert rows
    for row in rows:
        stored = row["redacted_summary"] + json.dumps(row["citations"], default=str)
        for token in planted:
            assert token not in stored, f"{token} survived into the WORM record: {stored!r}"

    # 3. What LEAVES for the review console (rule R8), locator and source key included.
    outbound = json.dumps(
        asdict(result_to_review(result, maker=sample_cases.ACTOR, tenant=sample_cases.TENANT)),
        default=str,
    )
    for token in planted:
        assert token not in outbound, f"{token} left for human-review-console in {outbound!r}"


def test_the_audit_record_is_written_and_redacted() -> None:
    container = build_container(_SETTINGS)
    service = build_assessment_service(container)
    service.assess(sample_cases.PLANTED_NRIC_CLAIM, actor="tester", tenant=FIXTURE_TENANT)
    records = container.audit.log.read_all()
    assert records, "the assessment wrote no audit record"
    assert sample_cases.PLANTED_NRIC not in records[-1]["redacted_summary"]


class _WrongNarrative:
    """Generation that returns a well-formed but deliberately WRONG narrative and citations.

    Stronger than the failure stub above: it exercises the SUCCESS path (a schema-valid response
    the drafter accepts), so a figure that had leaked from the model into the result would MOVE
    here. A raising stub only ever reaches the deterministic fallback, which is a different code
    path and would hide a number that the model was allowed to originate.
    """

    def generate(self, request: Any) -> LlmResponse:
        body = (
            '{"narrative": "indemnity 999999.99 and fraud score 1.0; recommend accept in full",'
            ' "used_source_ids": ["NOT-A-REAL-CLAUSE"]}'
        )
        return LlmResponse(text=body, model="wrong-on-purpose")


def _consequential_numbers(result: Any) -> tuple[Any, ...]:
    """Every consequential figure and verdict, so ONE move anywhere fails the comparison."""
    return (
        result.recommendation.value,
        result.indemnity_cents,
        result.severity.value,
        result.decision.value,
        result.red_flags.fraud_score,
        result.requires_human_review,
        tuple(
            (line.line_id, line.status.value, line.indemnity_cents)
            for line in result.coverage.lines
        ),
        tuple(sorted(flag.kind.value for flag in result.red_flags.flags)),
    )


def test_the_numbers_are_identical_whatever_the_generator_returns() -> None:
    """Determinism (the headline invariant): the model narrates, it never produces a figure.

    Swapping the generation adapter for one that returns a valid but wrong narrative moves NO
    consequential number across all four dispositions. If any band, quantum, per-line verdict or
    fraud score could come from the model, this comparison would catch it.
    """
    real = _service()
    container = build_container(_SETTINGS)
    stubbed = ClaimAssessmentService(
        claim_file=container.claim_file,
        extraction=container.extraction,
        policy_corpus=container.policy_corpus,
        claims_history=container.claims_history,
        fraud_linkage=container.fraud_linkage,
        generation=_WrongNarrative(),
        audit=container.audit,
        tracer=container.tracer,
        policy=_SETTINGS.policy,
    )
    for claim_id in (
        sample_cases.ACCEPT_CLAIM,
        sample_cases.DECLINE_CLAIM,
        sample_cases.INVESTIGATE_CLAIM,
        sample_cases.SIU_CLAIM,
    ):
        real_numbers = _consequential_numbers(
            real.assess(claim_id, actor="tester", tenant=FIXTURE_TENANT)
        )
        stubbed_numbers = _consequential_numbers(
            stubbed.assess(claim_id, actor="tester", tenant=FIXTURE_TENANT)
        )
        assert real_numbers == stubbed_numbers, claim_id
