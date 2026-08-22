"""Rule R8: an escalated assessment is ROUTED to Hrz7, not left in a per-repo boolean.

This is the standing gate for the failure the rule exists to prevent. A repo can set
``requires_human_review = True``, pass every other test, and still auto-execute in practice
because nothing ever reads the flag. So the assertions here are about the ROUTING, not the flag:
every assessment produces an outbound review (they are all consequential), a critical one demands
dual control, the payload leaves redacted, and the on-prem placeholder refuses rather than
swallowing the escalation.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from claims_integrity_investigator.adapters.gcp.review_router import (
    CloudReviewRouter,
)
from claims_integrity_investigator.adapters.local._fixtures import FIXTURE_TENANT
from claims_integrity_investigator.adapters.local.review_router import (
    LocalReviewRouter,
)
from claims_integrity_investigator.adapters.onprem.review_router import (
    OnPremReviewRouter,
)
from claims_integrity_investigator.api.app import (
    app,
)
from claims_integrity_investigator.config import (
    Settings,
    build_container,
)
from claims_integrity_investigator.domain.assessment_service import (
    build_assessment_service,
)
from claims_integrity_investigator.domain.kernel import (
    Severity,
)
from claims_integrity_investigator.domain.models import (
    ClaimAssessment,
)

from tests.fixtures import sample_cases


def _settings(profile: str = "local") -> Settings:
    return Settings(profile=profile, audit_path=":memory:", tenant=sample_cases.TENANT)


def _assess(claim_id: str) -> ClaimAssessment:
    service = build_assessment_service(build_container(_settings()))
    return service.assess(claim_id, actor="adjuster@insurer.example", tenant=FIXTURE_TENANT)


def test_an_assessment_produces_an_outbound_review() -> None:
    router = LocalReviewRouter(_settings())
    ref = router.route(_assess(sample_cases.ACCEPT_CLAIM), maker="adjuster@insurer.example")
    assert ref, "routing must return a reference, so the caller can record where it went"
    pending = router.outbox.pending()
    assert len(pending) == 1
    review = pending[0].review
    assert review.maker == "adjuster@insurer.example"
    assert review.tenant == sample_cases.TENANT
    assert review.source_key, "a durable outbox needs an idempotency key"


def test_a_siu_referral_demands_dual_control() -> None:
    router = LocalReviewRouter(_settings())
    router.route(_assess(sample_cases.SIU_CLAIM), maker="adjuster@insurer.example")
    review = router.outbox.pending()[0].review
    assert review.severity == Severity.CRITICAL.value
    assert review.required_approvals == 2


def test_the_payload_is_redacted_before_it_leaves_the_process() -> None:
    """Hrz7 is a shared sink; a raw identifier must never reach the wire."""
    router = LocalReviewRouter(_settings())
    router.route(sample_cases.planted_pii_assessment(), maker="adjuster@insurer.example")
    review = router.outbox.pending()[0].review
    wire = repr(review.to_payload())
    assert sample_cases.PLANTED_NRIC not in wire
    assert "REDACTED" in wire


def test_the_managed_router_refuses_when_no_console_is_configured() -> None:
    """An escalation with nowhere to go must fail loudly, not return as if it were reviewed."""
    router = CloudReviewRouter(Settings(profile="gcp", audit_path=":memory:", review_url=""))
    with pytest.raises(RuntimeError, match="R8"):
        router.route(sample_cases.planted_pii_assessment(), maker="adjuster@insurer.example")


def test_the_onprem_placeholder_refuses_rather_than_dropping_the_escalation() -> None:
    router = OnPremReviewRouter(_settings("onprem"))
    with pytest.raises(NotImplementedError, match="R8"):
        router.route(sample_cases.planted_pii_assessment(), maker="adjuster@insurer.example")


def test_the_api_routes_the_escalation_in_the_same_request() -> None:
    """The serving path, not just the adapter: an escalation must not depend on a later job."""
    client = TestClient(app, client=("127.0.0.1", 50000))
    assessed = client.post(
        "/v1/assess",
        json={"claim_id": sample_cases.SIU_CLAIM},
        headers={"X-Dev-Persona": "auditor"},
    ).json()
    assert assessed["requires_human_review"] is True
    assert assessed["review_ref"], "an escalation with no routing reference went nowhere"
    assert assessed["recommendation"] == "siu_refer"

    # The routed item then shows up in the SIU queue on the same process.
    queue = client.get("/v1/siu-queue", headers={"X-Dev-Persona": "auditor"}).json()
    assert any(item["claim_id"] == sample_cases.SIU_CLAIM for item in queue)
