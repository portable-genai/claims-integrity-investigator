"""The assessment path opens ONE span, and that span carries no content.

A trace backend is not the WORM audit trail. It has no redaction stage, no retention policy
written against a regulator's requirement, and a far wider read audience than the audit store.
So the value of tracing the assessment path depends entirely on the span carrying structural
attributes only: which action, whose, how long. A claim id, a claimant, a claim file fragment
or the drafted narrative reaching a span has left the boundary the redact-before-model and
redact-before-audit calls exist to hold, and it has left it silently.

The content case drives the claim whose FNOL free text carries a planted NRIC, so the check
runs against input that would actually leak if any attribute were content-shaped.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

import pytest

from claims_integrity_investigator.adapters.local._fixtures import FIXTURE_TENANT
from claims_integrity_investigator.config import Settings, build_container
from claims_integrity_investigator.domain.assessment_service import ClaimAssessmentService
from claims_integrity_investigator.domain.models import ClaimAssessment

from tests.fixtures import sample_cases

#: Every attribute key the assess span is allowed to carry. A disposition that started
#: explaining itself on the span (a recommendation, a claimant, a narrative fragment) would
#: widen this set, which is the point of asserting on the set rather than on individual keys.
_ASSESS_KEYS = {"action", "actor"}

_SETTINGS = Settings(profile="local", audit_path=":memory:")


class _RecordingTracer:
    """Captures every span name and attribute so the test can inspect what was emitted."""

    def __init__(self) -> None:
        self.spans: list[tuple[str, dict[str, str]]] = []

    @contextmanager
    def span(self, name: str, **attributes: str) -> Iterator[None]:
        self.spans.append((name, dict(attributes)))
        yield

    def record_token_usage(self, usage: object, model: str) -> None:
        return None


def _assess(claim_id: str) -> tuple[_RecordingTracer, ClaimAssessment]:
    """The REAL local adapters for every port except the tracer under inspection."""
    container = build_container(_SETTINGS)
    tracer = _RecordingTracer()
    service = ClaimAssessmentService(
        claim_file=container.claim_file,
        extraction=container.extraction,
        policy_corpus=container.policy_corpus,
        claims_history=container.claims_history,
        fraud_linkage=container.fraud_linkage,
        generation=container.generation,
        audit=container.audit,
        tracer=tracer,
        policy=_SETTINGS.policy,
    )
    result = service.assess(claim_id, actor=sample_cases.ACTOR, tenant=FIXTURE_TENANT)
    return tracer, result


def _emitted(tracer: _RecordingTracer) -> str:
    """Every span name, attribute KEY and attribute VALUE, as one searchable blob."""
    parts: list[str] = []
    for name, attributes in tracer.spans:
        parts.append(name)
        parts.extend(attributes)
        parts.extend(attributes.values())
    return " ".join(parts)


def test_assessing_one_claim_opens_exactly_one_named_span() -> None:
    tracer, _ = _assess(sample_cases.ACCEPT_CLAIM)
    assert [name for name, _ in tracer.spans] == ["claims.assess"]


def test_the_span_carries_the_structural_attributes_an_operator_needs() -> None:
    """Enough to answer "whose assessment is slow", and nothing more."""
    tracer, _ = _assess(sample_cases.ACCEPT_CLAIM)
    _, attributes = tracer.spans[0]
    assert attributes["action"] == "assess_claim"
    assert attributes["actor"] == sample_cases.ACTOR


@pytest.mark.parametrize(
    "claim_id",
    [
        sample_cases.ACCEPT_CLAIM,
        sample_cases.DECLINE_CLAIM,
        sample_cases.INVESTIGATE_CLAIM,
        sample_cases.SIU_CLAIM,
    ],
    ids=["accept", "decline", "investigate", "siu_refer"],
)
def test_the_attribute_set_is_a_fixed_allowlist_whatever_the_disposition(claim_id: str) -> None:
    """An SIU referral must not start attaching its red flags to the span to explain itself."""
    tracer, _ = _assess(claim_id)
    for _, attributes in tracer.spans:
        assert set(attributes) == _ASSESS_KEYS


def test_no_span_attribute_carries_claim_content_or_the_planted_identifier() -> None:
    """The claim used here has an NRIC planted in its FNOL text, so a leak would show."""
    tracer, result = _assess(sample_cases.PLANTED_NRIC_CLAIM)
    emitted = _emitted(tracer)

    forbidden: list[str] = [
        sample_cases.PLANTED_NRIC,
        sample_cases.PLANTED_NRIC_CLAIM,
        result.subject,
        result.policy_ref,
        # The summary and the drafted narrative are the other content-shaped values in reach.
        result.summary,
        result.narrative,
    ]
    for literal in forbidden:
        assert literal, "an empty needle would pass this test for the wrong reason"
        assert literal not in emitted, f"a span attribute carried {literal!r}"
        assert literal.lower() not in emitted.lower(), f"a span attribute carried {literal!r}"


def test_every_emitted_attribute_value_is_a_string_the_port_declares() -> None:
    """``span(name, **attributes: str)``: a non-string would serialise however the SDK felt."""
    tracer, _ = _assess(sample_cases.SIU_CLAIM)
    values: list[Any] = [v for _, attributes in tracer.spans for v in attributes.values()]
    assert values
    assert all(isinstance(value, str) for value in values)
