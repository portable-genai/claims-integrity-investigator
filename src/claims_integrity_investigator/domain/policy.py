"""The bank-owned policy numbers, lifted out of the engines into one frozen dataclass.

The red-flag uplifts, the fraud-score thresholds and the late-notification window are the
CLIENT's numbers, not the code's. They live here as a frozen :class:`AssessmentPolicy` with an
``as_of`` stamp and are loaded from the ``policy:`` block of ``config/settings.yaml`` (see
``config.load_policy``), so an adopter tunes them without a code edit and every run records
which policy version produced a figure. The engines take a policy by construction and read every
number off it; none is a module constant hiding in an engine.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .models import RedFlagKind


def _default_uplifts() -> dict[str, float]:
    """The shipped per-kind uplift weights (fictional, tune per adopter)."""
    return {
        RedFlagKind.LATE_NOTIFICATION.value: 0.10,
        RedFlagKind.STAGED_LOSS.value: 0.25,
        RedFlagKind.INVOICE_ANOMALY.value: 0.15,
        RedFlagKind.CLAIMS_VELOCITY.value: 0.20,
        RedFlagKind.ORGANISED_FRAUD_LINK.value: 0.40,
    }


def _default_markers() -> tuple[str, ...]:
    """Fictional staged-loss marker phrases the adjuster-note scan looks for."""
    return (
        "no forced entry",
        "receipts dated after loss",
        "prior identical claim",
        "vehicle already damaged",
        "witness unreachable",
    )


@dataclass(frozen=True, slots=True)
class AssessmentPolicy:
    """Frozen, adopter-owned thresholds and weights. Loaded from ``settings.yaml`` ``policy:``."""

    #: Policy version stamp, so an assessment records which numbers produced it.
    as_of: str = "2026-01-01"
    #: Days after the loss date beyond which notification counts as late.
    late_notification_days: int = 30
    #: The window and count that make prior-claim velocity a flag.
    velocity_window_days: int = 365
    velocity_threshold: int = 3
    #: A claimed line at or above this many cents that is an exact multiple of
    #: ``round_amount_unit_cents`` is treated as a suspicious round-number invoice.
    round_amount_floor_cents: int = 500_00
    round_amount_unit_cents: int = 1_000_00
    #: Fraud-score baseline and the cap on summed uplift (cribbed from the pKYC rescore shape).
    fraud_baseline: float = 0.05
    max_uplift: float = 0.80
    #: Fraud-score bands: at or above refer to SIU; at or above investigate; else accept/decline
    #: on the coverage outcome.
    siu_refer_score: float = 0.55
    investigate_score: float = 0.30
    uplifts: dict[str, float] = field(default_factory=_default_uplifts)
    staged_loss_markers: tuple[str, ...] = field(default_factory=_default_markers)

    def uplift_for(self, kind: RedFlagKind) -> float:
        """The configured uplift weight for a red-flag kind (0.0 if the adopter removed it)."""
        return float(self.uplifts.get(kind.value, 0.0))
