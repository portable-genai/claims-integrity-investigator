"""API surface: verified-principal identity, fail-closed S2S, security headers.

The client comes from the shared ``api_client`` fixture, which pins a loopback peer: the
app-object exposure guard refuses the unauthenticated local posture to any other peer, and
TestClient's default peer is the literal host "testclient".
"""

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from tests.fixtures import sample_cases

_TOKEN_ENV = "CLAIMSINTEG_S2S_TOKEN"


def test_assess_uses_the_verified_principal_as_actor(api_client: TestClient) -> None:
    resp = api_client.post(
        "/v1/assess",
        json={"claim_id": sample_cases.SIU_CLAIM},
        headers={"X-Dev-Persona": "auditor"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["recommendation"] == "siu_refer"
    assert body["severity"] == "critical"
    assert body["requires_human_review"] is True
    # Rule R8: the escalation was routed, not merely flagged (see test_review_routing.py).
    assert body["review_ref"]
    # The consequential figures are the engine's and reach the caller cited.
    assert body["coverage"], "the coverage arithmetic must be returned line by line"
    assert body["citations"], "every assessment must carry provenance"


def test_assess_returns_the_four_dispositions(api_client: TestClient) -> None:
    """Each fixture claim lands on the disposition the engine computes, deterministically."""
    expected = {
        sample_cases.ACCEPT_CLAIM: "accept",
        sample_cases.DECLINE_CLAIM: "decline",
        sample_cases.INVESTIGATE_CLAIM: "investigate",
        sample_cases.SIU_CLAIM: "siu_refer",
    }
    for claim_id, disposition in expected.items():
        body = api_client.post(
            "/v1/assess",
            json={"claim_id": claim_id},
            headers={"X-Dev-Persona": "auditor"},
        ).json()
        assert body["recommendation"] == disposition, claim_id


def test_a_claim_of_another_tenant_is_not_assessable(api_client: TestClient) -> None:
    """Object-level authorization: naming a claim id is not entitlement to the file behind it.

    The verified principal `other-tenant` belongs to `other-bank`. The claim-file port took no
    principal at all, so any authenticated caller who named a claim id received that claimant's
    whole file, had it assessed, and had the result routed to a console under their own tenant.
    The refusal is 404 rather than 403: telling the caller the id exists somewhere else is itself
    a disclosure.
    """
    resp = api_client.post(
        "/v1/assess",
        json={"claim_id": sample_cases.SIU_CLAIM},
        headers={"X-Dev-Persona": "other-tenant"},
    )
    assert resp.status_code == 404, (
        f"a foreign tenant assessed the claim: {resp.status_code} {resp.text[:200]}"
    )


def test_the_siu_queue_is_scoped_to_the_principals_tenant(api_client: TestClient) -> None:
    """The queue is a query, and an unscoped query is the same defect with no id to guess."""
    routed = api_client.post(
        "/v1/assess",
        json={"claim_id": sample_cases.SIU_CLAIM},
        headers={"X-Dev-Persona": "analyst"},
    )
    assert routed.status_code == 200
    own = api_client.get("/v1/siu-queue", headers={"X-Dev-Persona": "analyst"})
    other = api_client.get("/v1/siu-queue", headers={"X-Dev-Persona": "other-tenant"})
    assert own.status_code == 200 and other.status_code == 200
    assert own.json(), "the home tenant must still see what it routed"
    assert other.json() == [], f"a foreign tenant read the review queue: {other.json()}"


def test_unknown_persona_is_401(api_client: TestClient) -> None:
    resp = api_client.post(
        "/v1/assess",
        json={"claim_id": sample_cases.ACCEPT_CLAIM},
        headers={"X-Dev-Persona": "ghost"},
    )
    assert resp.status_code == 401


def test_healthz_reports_profile_and_region(api_client: TestClient) -> None:
    body = api_client.get("/healthz").json()
    assert body["status"] == "ok"
    assert body["profile"] == "local"
    assert body["region"] == "asia-southeast1"


def test_security_headers_present(api_client: TestClient) -> None:
    headers = api_client.get("/healthz").headers
    assert headers["Content-Security-Policy"] == "frame-ancestors 'self'"
    assert headers["X-Content-Type-Options"] == "nosniff"


@pytest.fixture()
def token_env(monkeypatch: pytest.MonkeyPatch) -> Iterator[str]:
    monkeypatch.setenv(_TOKEN_ENV, "s3cret-service-token")
    yield "s3cret-service-token"


def test_s2s_endpoint_open_when_secret_unset(
    api_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv(_TOKEN_ENV, raising=False)
    assert api_client.post("/v1/audit/ping").status_code == 200


def test_s2s_endpoint_rejects_missing_token_when_enforced(
    api_client: TestClient, token_env: str
) -> None:
    assert api_client.post("/v1/audit/ping").status_code == 401


def test_s2s_endpoint_accepts_correct_token(api_client: TestClient, token_env: str) -> None:
    resp = api_client.post("/v1/audit/ping", headers={"Authorization": f"Bearer {token_env}"})
    assert resp.status_code == 200
