"""ONE canonical request per port, shared by the structural and behavioural contract suites.

Parity means the same request through every implementation, so the request needs a single home.
Retyping it per suite is how two "parity" tests end up asserting different things.

Each :class:`PortCase` answers three questions about one port:

* ``invoke``   : what a single canonical call to this port looks like;
* ``answered`` : what it means for the OFFLINE family to have actually answered (a port that
  returns ``None`` and records nothing has not answered, it has merely not raised);
* ``managed_refusal`` : what the MANAGED family must do when called with no cloud reachable.
  Never a silent success: either it refuses because it is unconfigured, or its lazy SDK import
  fails. Both are honest; returning as if the work happened is not.

Adding a port means adding a case here. ``test_port_parity.py`` fails the build if this table
and the port map ever disagree, so the touch list in ``CONTRIBUTING.md`` is enforced rather than
merely written down.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from agent_eval_kit import EvalReport
from hex_service_kit.identity import IdentityError, Principal, RequestContext
from hex_service_kit.observability import TokenUsage

from claims_integrity_investigator.adapters.local._fixtures import FIXTURE_TENANT
from claims_integrity_investigator.domain.kernel import (
    AuditEvent,
    Citation,
    Decision,
    Severity,
)
from claims_integrity_investigator.domain.models import (
    ClaimAssessment,
    CoverageAssessment,
    CoverageLine,
    CoverStatus,
    LlmMessage,
    LlmRequest,
    Recommendation,
    RedFlagAssessment,
    RetrievalQuery,
)

from tests.fixtures import sample_cases

#: The audit record every audit-port implementation is handed. Already redacted, as the port
#: requires: a raw identifier must never reach a WORM record.
CANONICAL_EVENT = AuditEvent(
    action="assess_claim",
    actor=sample_cases.ACTOR,
    decision=Decision.ESCALATED,
    severity=Severity.CRITICAL,
    redacted_summary="CLM-1004: siu_refer; indemnity 19,500.00 of 20,000.00 claimed; fraud 0.75",
    citations=(Citation(source_id="CL-MOTOR-1", title="Motor repair cover", snippet="section 1"),),
)

_COVERAGE = CoverageAssessment(
    policy_ref="POL-MOTOR-088",
    lines=(
        CoverageLine(
            line_id="L1",
            category="motor_repair",
            claimed_cents=1_200_000,
            status=CoverStatus.EXCESS,
            indemnity_cents=1_150_000,
            reason="less the 500.00 policy excess",
            citations=(Citation(source_id="CL-MOTOR-1", title="Motor repair cover", snippet="s1"),),
        ),
    ),
    total_claimed_cents=1_200_000,
    total_indemnity_cents=1_150_000,
)

#: The escalated assessment every review-router implementation is handed (rule R8's payload).
CANONICAL_RESULT = ClaimAssessment(
    claim_id="CLM-1004",
    subject="Priya Nair (FICTIONAL)",
    policy_ref="POL-MOTOR-088",
    recommendation=Recommendation.SIU_REFER,
    severity=Severity.CRITICAL,
    decision=Decision.ESCALATED,
    coverage=_COVERAGE,
    red_flags=RedFlagAssessment(flags=(), fraud_score=0.75),
    indemnity_cents=1_150_000,
    summary="CLM-1004: siu_refer; indemnity 11,500.00 of 12,000.00 claimed; fraud 0.75",
    narrative="[DRAFT] restated engine figures.",
    requires_human_review=True,
    citations=(Citation(source_id="CL-MOTOR-1", title="Motor repair cover", snippet="section 1"),),
)

#: The inbound transport context every identity implementation is handed.
CANONICAL_CONTEXT = RequestContext(headers={"x-dev-persona": "auditor"})

#: One canonical call for each data/generation port.
CANONICAL_CLAIM_ID = sample_cases.ACCEPT_CLAIM
CANONICAL_SUBJECT = "Ravi Kumar (FICTIONAL)"
CANONICAL_QUERY = RetrievalQuery(
    text="policy POL-HOME-001 coverage exclusions contents",
    filters={"policy_ref": "POL-HOME-001"},
)
CANONICAL_LLM_REQUEST = LlmRequest(
    messages=(
        LlmMessage(
            role="user",
            content=(
                "Recommendation (fixed): accept\n\nTotals for policy POL-HOME-001: claimed "
                "500.00; indemnity 480.00.\n\nFraud score 0.05.\n\nRetrieved policy wording:\n"
                "[CL-CONTENTS-1] Home contents cover: section 2."
            ),
        ),
    ),
    system_instruction="restate the figures",
    response_schema={"type": "object"},
)


@dataclass(frozen=True, slots=True)
class PortCase:
    """One port's canonical call plus the two verdicts the parity suites need."""

    invoke: Callable[[Any], Any]
    answered: Callable[[Any, Any], bool]
    managed_refusal: tuple[type[BaseException], ...]
    detail: str


def _audit_invoke(adapter: Any) -> Any:
    return adapter.record(CANONICAL_EVENT)


def _audit_answered(adapter: Any, _result: Any) -> bool:
    stored = adapter.log.read_all()
    return bool(stored) and stored[-1]["actor"] == sample_cases.ACTOR and adapter.verify().ok


def _identity_invoke(adapter: Any) -> Any:
    return adapter.resolve(CANONICAL_CONTEXT)


def _identity_answered(_adapter: Any, result: Any) -> bool:
    return isinstance(result, Principal) and bool(result.actor)


def _review_invoke(adapter: Any) -> Any:
    return adapter.route(CANONICAL_RESULT, maker=sample_cases.ACTOR, tenant=sample_cases.TENANT)


def _review_answered(adapter: Any, result: Any) -> bool:
    return bool(result) and len(adapter.outbox.pending()) == 1


def _claim_file_invoke(adapter: Any) -> Any:
    return adapter.fetch(CANONICAL_CLAIM_ID, tenant=FIXTURE_TENANT)


def _claim_file_answered(_adapter: Any, result: Any) -> bool:
    return bool(getattr(result, "documents", ())) and result.claim_id == CANONICAL_CLAIM_ID


def _extraction_invoke(adapter: Any) -> Any:
    from claims_integrity_investigator.adapters.local._fixtures import CLAIM_FILES

    return adapter.extract(CLAIM_FILES[CANONICAL_CLAIM_ID])


def _extraction_answered(_adapter: Any, result: Any) -> bool:
    return bool(getattr(result, "lines", ())) and bool(result.loss_date)


def _policy_corpus_invoke(adapter: Any) -> Any:
    return adapter.retrieve(CANONICAL_QUERY)


def _policy_corpus_answered(_adapter: Any, result: Any) -> bool:
    return bool(result) and all(p.citation.source_id for p in result)


def _claims_history_invoke(adapter: Any) -> Any:
    return adapter.history(CANONICAL_SUBJECT)


def _claims_history_answered(_adapter: Any, result: Any) -> bool:
    return result is not None and result.subject == CANONICAL_SUBJECT


def _fraud_linkage_invoke(adapter: Any) -> Any:
    return adapter.linkage(CANONICAL_SUBJECT)


def _fraud_linkage_answered(_adapter: Any, result: Any) -> bool:
    return result is not None and result.subject == CANONICAL_SUBJECT


def _generation_invoke(adapter: Any) -> Any:
    return adapter.generate(CANONICAL_LLM_REQUEST)


def _generation_answered(_adapter: Any, result: Any) -> bool:
    return bool(getattr(result, "text", ""))


def _tracer_invoke(adapter: Any) -> Any:
    with adapter.span("canonical.unit", action="canonical"):
        adapter.record_token_usage(TokenUsage(input_tokens=7, output_tokens=2), "canonical-model")
    return True


def _tracer_answered(adapter: Any, result: Any) -> bool:
    return bool(result)


def _evaluation_invoke(adapter: Any) -> Any:
    return adapter.evaluate("eval/datasets/canonical.jsonl")


def _evaluation_answered(adapter: Any, result: Any) -> bool:
    return isinstance(result, EvalReport) and result.dataset.endswith("canonical.jsonl")


CANONICAL_CALLS: dict[str, PortCase] = {
    "audit": PortCase(
        invoke=_audit_invoke,
        answered=_audit_answered,
        # The lazy `google.cloud` import is the first thing the managed sink does.
        managed_refusal=(ImportError,),
        detail="write one already-redacted WORM record",
    ),
    "claim_file": PortCase(
        invoke=_claim_file_invoke,
        answered=_claim_file_answered,
        # The lazy `google.cloud` import is the first thing the managed adapter does.
        managed_refusal=(ImportError,),
        detail="fetch one raw claim file",
    ),
    "claims_history": PortCase(
        invoke=_claims_history_invoke,
        answered=_claims_history_answered,
        managed_refusal=(ImportError,),
        detail="read one claimant's prior-claims record",
    ),
    "extraction": PortCase(
        invoke=_extraction_invoke,
        answered=_extraction_answered,
        managed_refusal=(ImportError,),
        detail="extract structured evidence from a claim file",
    ),
    "fraud_linkage": PortCase(
        invoke=_fraud_linkage_invoke,
        answered=_fraud_linkage_answered,
        managed_refusal=(ImportError,),
        detail="read one claimant's organised-fraud linkage",
    ),
    "generation": PortCase(
        invoke=_generation_invoke,
        answered=_generation_answered,
        managed_refusal=(ImportError,),
        detail="draft the cited narrative",
    ),
    "identity": PortCase(
        invoke=_identity_invoke,
        answered=_identity_answered,
        # No IAP assertion header offline, so the managed adapter refuses before importing.
        managed_refusal=(IdentityError,),
        detail="resolve a verified principal from transport context",
    ),
    "policy_corpus": PortCase(
        invoke=_policy_corpus_invoke,
        answered=_policy_corpus_answered,
        # Hrz2 is a hard dependency: with no endpoint configured the governed adapter REFUSES
        # rather than falling back to an ungoverned search.
        managed_refusal=(RuntimeError,),
        detail="retrieve governed policy wording (Hrz2)",
    ),
    "review_router": PortCase(
        invoke=_review_invoke,
        answered=_review_answered,
        # Rule R8: with no console configured the managed router must refuse, not swallow.
        managed_refusal=(RuntimeError,),
        detail="route one escalated assessment to human review",
    ),
    "tracer": PortCase(
        invoke=_tracer_invoke,
        answered=_tracer_answered,
        # NOTHING. Tracing is not essential to correctness, so the managed adapter must not refuse
        # offline either: with no SDK it degrades to a no-op and the traced body still runs. An
        # adapter that raised here would take a request down over a diagnostic.
        managed_refusal=(),
        detail="open one span and report the cost of a model call",
    ),
    "evaluation": PortCase(
        invoke=_evaluation_invoke,
        answered=_evaluation_answered,
        # The managed gate reaches Hrz4 over HTTP, which is unreachable offline.
        managed_refusal=(Exception,),
        detail="score one golden dataset through the promotion authority",
    ),
}
