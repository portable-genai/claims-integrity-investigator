"""The service half of the model pills: which model ANSWERED, and whether it searched.

The console shows two pills at the top right: the model that answered the last request, and
``Search`` when that answer used an online search tool. Both come from response headers the kit
emits (``install_answer_provenance`` in ``api/app.py``) for whatever the model adapters NOTED as
they called. Before a request is answered the pill shows ``generator_model`` from ``/healthz``,
so that value must be the model the bound adapter calls, never one a configuration flag names
while the adapter calls another.

The only model call here is the assessment narrative. Under ``local`` it is the deterministic
narrator, which answers as the stub ``generator_model`` names. The managed Gemini narrator is a
deployment-wired placeholder that raises before calling anything, so it notes nothing and the
pill keeps naming ``managed-not-implemented``.
"""

from __future__ import annotations

import dataclasses
from collections.abc import Iterator
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from hex_service_kit import provenance

from claims_integrity_investigator import config
from claims_integrity_investigator.adapters.gcp.generation import CloudGenerationAdapter
from claims_integrity_investigator.adapters.local.generation import (
    STUB_MODEL,
    LocalGenerationAdapter,
)
from claims_integrity_investigator.api import app as app_module
from claims_integrity_investigator.domain.models import LlmMessage, LlmRequest, LlmResponse

from tests import REPO_ROOT
from tests.conftest import local_settings
from tests.fixtures import sample_cases

ANSWERED_BY = "x-answered-by"
SEARCH_USED = "x-search-used"


@pytest.fixture()
def local_client(monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    """The API under ``local`` whatever the shell exported: CI runs with no profile set."""
    monkeypatch.setenv(config._PROFILE_ENV, "local")
    app_module._container.cache_clear()
    with TestClient(app_module.app, client=("127.0.0.1", 50000)) as client:
        yield client
    app_module._container.cache_clear()


def _assess(client: TestClient) -> dict[str, str]:
    response = client.post(
        "/v1/assess",
        json={"claim_id": sample_cases.SIU_CLAIM},
        headers={"X-Dev-Persona": "auditor"},
    )
    assert response.status_code == 200, response.text
    return dict(response.headers)


def test_the_local_narrator_answers_as_the_stub_the_pill_first_names(
    local_client: TestClient,
) -> None:
    """Under ``local`` the pill before and after the answer name the same stub."""
    headers = _assess(local_client)
    assert headers[ANSWERED_BY] == STUB_MODEL
    assert SEARCH_USED not in headers
    assert local_settings().generator_model == STUB_MODEL


def test_a_call_that_searched_says_so_and_the_next_request_starts_fresh(
    local_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    original = LocalGenerationAdapter.generate

    def searching(self: LocalGenerationAdapter, request: LlmRequest) -> LlmResponse:
        provenance.note_model("fake-searching-model")
        provenance.note_search()
        return original(self, request)

    monkeypatch.setattr(LocalGenerationAdapter, "generate", searching)
    headers = _assess(local_client)
    assert headers[ANSWERED_BY] == f"fake-searching-model, {STUB_MODEL}"
    assert headers[SEARCH_USED] == "true"
    monkeypatch.setattr(LocalGenerationAdapter, "generate", original)
    headers = _assess(local_client)
    assert headers[ANSWERED_BY] == STUB_MODEL
    assert SEARCH_USED not in headers


def test_the_narrative_is_drafted_with_no_temperature(
    local_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Narration restates figures the engine fixed, so it samples freely: nothing is sent."""
    seen: list[LlmRequest] = []
    original = LocalGenerationAdapter.generate

    def recording(self: LocalGenerationAdapter, request: LlmRequest) -> LlmResponse:
        seen.append(request)
        return original(self, request)

    monkeypatch.setattr(LocalGenerationAdapter, "generate", recording)
    _assess(local_client)
    assert seen, "the assessment never called the narrator"
    assert all(request.temperature is None for request in seen)


def test_the_managed_placeholder_notes_nothing_because_it_never_answers() -> None:
    """A narrator that raises before calling a model must not put a model on screen."""
    settings = dataclasses.replace(local_settings(), profile="gcp")
    request = LlmRequest(messages=(LlmMessage(role="user", content="x"),))
    with provenance.scope() as record, pytest.raises((ImportError, NotImplementedError)):
        CloudGenerationAdapter(settings).generate(request)
    assert record.models == []
    assert record.search_used is False
    assert settings.generator_model == "managed-not-implemented"


def test_no_flag_swaps_in_a_model_the_adapter_never_calls() -> None:
    """The latent false banner: a flag that moved the pill but not the model that answered."""
    models = SimpleNamespace(
        reasoning="the-model-the-adapter-calls",
        hard_reasoning="a-model-nobody-calls",
        use_hard_reasoning=True,
    )
    named = config._model_from_settings(SimpleNamespace(models=models), "models.reasoning")
    assert named == "the-model-the-adapter-calls"


def test_the_hard_reasoning_flag_does_not_exist() -> None:
    settings_file = (REPO_ROOT / "config" / "settings.yaml").read_text(encoding="utf-8")
    assert "use_hard_reasoning" not in settings_file
    for source in sorted((REPO_ROOT / "src").rglob("*.py")):
        assert "use_hard_reasoning" not in source.read_text(encoding="utf-8"), source
