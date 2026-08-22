"""The deterministic red-flag engine: each indicator provable-red, the score arithmetic exact.

Every rule is proved by a case that fires it and a near-identical case that does not, so the
metric cannot be structurally green. The fingerprints are asserted stable across re-runs, and
the clamped-score arithmetic is hand-computed as an independent oracle.
"""

from __future__ import annotations

from claims_integrity_investigator.domain.models import (
    ClaimLine,
    ClaimsHistory,
    ExtractedClaim,
    FraudLinkage,
    PriorClaim,
    RedFlagKind,
)
from claims_integrity_investigator.domain.policy import AssessmentPolicy
from claims_integrity_investigator.domain.red_flags import RedFlagEngine, signal_key

_POLICY = AssessmentPolicy()
_ENGINE = RedFlagEngine(policy=_POLICY)
_NO_HISTORY = ClaimsHistory(subject="X", prior_claims=())
_NO_LINK = FraudLinkage(subject="X", matched=False)


def _claim(
    *,
    loss: str = "2026-03-01",
    notified: str = "2026-03-05",
    lines: tuple[ClaimLine, ...] = (),
    notes: str = "",
    subject: str = "X",
) -> ExtractedClaim:
    return ExtractedClaim(
        claim_id="CLM-T",
        subject=subject,
        policy_ref="POL-T",
        loss_date=loss,
        notified_date=notified,
        lines=lines,
        adjuster_notes=notes,
    )


def _kinds(result: object) -> set[str]:
    return {flag.kind.value for flag in result.flags}  # type: ignore[attr-defined]


def test_late_notification_fires_only_beyond_the_window() -> None:
    late = _ENGINE.evaluate(_claim(notified="2026-05-01"), _NO_HISTORY, _NO_LINK)
    prompt = _ENGINE.evaluate(_claim(notified="2026-03-10"), _NO_HISTORY, _NO_LINK)
    assert RedFlagKind.LATE_NOTIFICATION.value in _kinds(late)
    assert RedFlagKind.LATE_NOTIFICATION.value not in _kinds(prompt)


def test_staged_loss_marker_fires_only_on_the_marker() -> None:
    flagged = _ENGINE.evaluate(
        _claim(notes="No forced entry to the property"), _NO_HISTORY, _NO_LINK
    )
    clean = _ENGINE.evaluate(_claim(notes="Attended site, all in order"), _NO_HISTORY, _NO_LINK)
    assert RedFlagKind.STAGED_LOSS.value in _kinds(flagged)
    assert RedFlagKind.STAGED_LOSS.value not in _kinds(clean)


def test_invoice_anomaly_fires_on_pre_loss_date_duplicate_and_round_amount() -> None:
    anomalous = _claim(
        lines=(
            ClaimLine(
                "L1",
                "tools",
                "kit",
                300_000,
                "inv:1",
                invoice_no="INV-1",
                invoice_date="2026-02-01",
            ),
        )
    )
    clean = _claim(
        lines=(
            ClaimLine(
                "L1",
                "tools",
                "kit",
                287_431,
                "inv:1",
                invoice_no="INV-1",
                invoice_date="2026-03-04",
            ),
        )
    )
    assert RedFlagKind.INVOICE_ANOMALY.value in _kinds(
        _ENGINE.evaluate(anomalous, _NO_HISTORY, _NO_LINK)
    )
    assert RedFlagKind.INVOICE_ANOMALY.value not in _kinds(
        _ENGINE.evaluate(clean, _NO_HISTORY, _NO_LINK)
    )


def test_claims_velocity_fires_at_the_threshold_but_not_below() -> None:
    priors = (
        PriorClaim("A", "2025-06-01"),
        PriorClaim("B", "2025-09-01"),
        PriorClaim("C", "2026-01-01"),
    )
    at_threshold = ClaimsHistory(subject="X", prior_claims=priors)
    below = ClaimsHistory(subject="X", prior_claims=priors[:2])
    assert RedFlagKind.CLAIMS_VELOCITY.value in _kinds(
        _ENGINE.evaluate(_claim(), at_threshold, _NO_LINK)
    )
    assert RedFlagKind.CLAIMS_VELOCITY.value not in _kinds(
        _ENGINE.evaluate(_claim(), below, _NO_LINK)
    )


def test_organised_fraud_link_fires_only_on_a_match() -> None:
    linked = FraudLinkage(subject="X", matched=True, ring_ref="RING-1", detail="ring")
    assert RedFlagKind.ORGANISED_FRAUD_LINK.value in _kinds(
        _ENGINE.evaluate(_claim(), _NO_HISTORY, linked)
    )
    assert RedFlagKind.ORGANISED_FRAUD_LINK.value not in _kinds(
        _ENGINE.evaluate(_claim(), _NO_HISTORY, _NO_LINK)
    )


def test_the_score_is_baseline_plus_capped_uplift_clamped() -> None:
    # Late (0.10) + one staged marker (0.25) + baseline 0.05 = 0.40, no cap needed.
    result = _ENGINE.evaluate(
        _claim(notified="2026-05-01", notes="No forced entry"), _NO_HISTORY, _NO_LINK
    )
    assert result.fraud_score == 0.40


def test_the_uplift_cap_holds() -> None:
    # Everything fires: summed uplift exceeds max_uplift (0.80), so score = 0.05 + 0.80 = 0.85.
    priors = (
        PriorClaim("A", "2025-06-01"),
        PriorClaim("B", "2025-09-01"),
        PriorClaim("C", "2026-01-01"),
    )
    linked = FraudLinkage(subject="X", matched=True, ring_ref="R", detail="d")
    lines = (
        ClaimLine("L1", "tools", "k", 300_000, "inv:1", invoice_no="I", invoice_date="2026-02-01"),
    )
    result = _ENGINE.evaluate(
        _claim(notified="2026-05-01", notes="No forced entry", lines=lines),
        ClaimsHistory(subject="X", prior_claims=priors),
        linked,
    )
    assert result.fraud_score == 0.85


def test_fingerprints_are_stable_across_reruns() -> None:
    claim = _claim(notified="2026-05-01")
    first = _ENGINE.evaluate(claim, _NO_HISTORY, _NO_LINK).flags[0].key
    second = _ENGINE.evaluate(claim, _NO_HISTORY, _NO_LINK).flags[0].key
    assert (
        first
        == second
        == signal_key(RedFlagKind.LATE_NOTIFICATION, "CLM-T", "2026-03-01", "2026-05-01")
    )
