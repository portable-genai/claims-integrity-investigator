"""The deterministic red-flag (fraud-indicator) engine: pure, replayable, provable-red.

Indicators raise a fraud score and set the claim up for human review; they are NEVER
conclusions (the Doc1 nominee/shell-indicator convention). Each indicator is a fingerprinted
:class:`RedFlag` with its own uplift and cited evidence, and the score is
``baseline + min(sum(uplifts), max_uplift)`` clamped to ``[0, 1]`` (the pKYC rescore shape). The
engine reads every number off the injected :class:`AssessmentPolicy`, so the adopter owns the
thresholds and no weight is a constant hiding here.

The claims-history velocity rule reads a claims-history record (the BigQuery linkage port,
offline-fixture-backed by default) and the organised-fraud rule reads a G-series linkage feed;
both arrive as raw data through ports, and the arithmetic that turns them into a score is here.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import date

from .kernel import Citation
from .models import (
    ClaimsHistory,
    ExtractedClaim,
    FraudLinkage,
    RedFlag,
    RedFlagAssessment,
    RedFlagKind,
    money,
)
from .policy import AssessmentPolicy


def signal_key(kind: RedFlagKind, *parts: str) -> str:
    """A stable fingerprint for one observed indicator: ``<kind>:<16 hex>``.

    Taken over the normalised identifying parts (case-folded, whitespace collapsed), so a re-run
    over the same evidence produces the same key and two runs diff exactly, while a genuinely
    different fact (another invoice, a different ring) produces a different key.
    """
    normalised = "|".join(" ".join(part.split()).casefold() for part in parts)
    digest = hashlib.sha256(f"{kind.value}|{normalised}".encode()).hexdigest()[:16]
    return f"{kind.value}:{digest}"


def _parse_date(value: str) -> date | None:
    try:
        return date.fromisoformat(value.strip())
    except (ValueError, AttributeError):
        return None


@dataclass(frozen=True, slots=True)
class RedFlagEngine:
    """Pure fraud-indicator detection and scoring, driven by an adopter-owned policy."""

    policy: AssessmentPolicy

    def evaluate(
        self,
        claim: ExtractedClaim,
        history: ClaimsHistory,
        linkage: FraudLinkage,
    ) -> RedFlagAssessment:
        """Raise the fraud indicators the evidence supports and return the clamped score."""
        flags: list[RedFlag] = []
        flags.extend(self._late_notification(claim))
        flags.extend(self._staged_loss(claim))
        flags.extend(self._invoice_anomalies(claim))
        flags.extend(self._velocity(claim, history))
        flags.extend(self._organised_fraud(linkage))

        raised = sum(flag.uplift for flag in flags)
        capped = min(raised, self.policy.max_uplift)
        score = max(0.0, min(1.0, self.policy.fraud_baseline + capped))
        return RedFlagAssessment(flags=tuple(flags), fraud_score=round(score, 4))

    # ------------------------------------------------------------------ #
    # Individual rules
    # ------------------------------------------------------------------ #
    def _late_notification(self, claim: ExtractedClaim) -> list[RedFlag]:
        loss = _parse_date(claim.loss_date)
        notified = _parse_date(claim.notified_date)
        if loss is None or notified is None:
            return []
        elapsed = (notified - loss).days
        if elapsed <= self.policy.late_notification_days:
            return []
        kind = RedFlagKind.LATE_NOTIFICATION
        return [
            RedFlag(
                kind=kind,
                key=signal_key(kind, claim.claim_id, claim.loss_date, claim.notified_date),
                uplift=self.policy.uplift_for(kind),
                reason=(
                    f"notified {elapsed} days after the loss, beyond the "
                    f"{self.policy.late_notification_days}-day window"
                ),
                citations=(
                    Citation(
                        source_id=f"{claim.claim_id}:dates",
                        title="Notification timing",
                        snippet=f"loss {claim.loss_date}, notified {claim.notified_date}",
                    ),
                ),
            )
        ]

    def _staged_loss(self, claim: ExtractedClaim) -> list[RedFlag]:
        notes = claim.adjuster_notes.casefold()
        flags: list[RedFlag] = []
        kind = RedFlagKind.STAGED_LOSS
        for marker in self.policy.staged_loss_markers:
            if marker.casefold() in notes:
                flags.append(
                    RedFlag(
                        kind=kind,
                        key=signal_key(kind, claim.claim_id, marker),
                        uplift=self.policy.uplift_for(kind),
                        reason=f"adjuster note contains the staged-loss marker {marker!r}",
                        citations=(
                            Citation(
                                source_id=f"{claim.claim_id}:adjuster",
                                title="Adjuster note",
                                snippet=marker,
                            ),
                        ),
                    )
                )
        return flags

    def _invoice_anomalies(self, claim: ExtractedClaim) -> list[RedFlag]:
        flags: list[RedFlag] = []
        kind = RedFlagKind.INVOICE_ANOMALY
        loss = _parse_date(claim.loss_date)
        seen_numbers: dict[str, str] = {}
        for line in claim.lines:
            reasons: list[str] = []
            if line.invoice_no and line.invoice_no in seen_numbers:
                reasons.append(
                    f"invoice number {line.invoice_no} duplicates line "
                    f"{seen_numbers[line.invoice_no]}"
                )
            if line.invoice_no:
                seen_numbers.setdefault(line.invoice_no, line.line_id)
            inv_date = _parse_date(line.invoice_date)
            if loss is not None and inv_date is not None and inv_date < loss:
                reasons.append(f"invoice dated {line.invoice_date}, before the loss")
            if self._is_round(line.claimed_cents):
                reasons.append(f"round-number amount {money(line.claimed_cents)}")
            if reasons:
                flags.append(
                    RedFlag(
                        kind=kind,
                        key=signal_key(kind, claim.claim_id, line.line_id),
                        uplift=self.policy.uplift_for(kind),
                        reason="; ".join(reasons),
                        citations=(
                            Citation(
                                source_id=line.doc_ref,
                                title=f"Invoice line {line.line_id}",
                                snippet=f"{line.description} ({money(line.claimed_cents)})",
                            ),
                        ),
                    )
                )
        return flags

    def _is_round(self, cents: int) -> bool:
        return (
            cents >= self.policy.round_amount_floor_cents
            and self.policy.round_amount_unit_cents > 0
            and cents % self.policy.round_amount_unit_cents == 0
        )

    def _velocity(self, claim: ExtractedClaim, history: ClaimsHistory) -> list[RedFlag]:
        notified = _parse_date(claim.notified_date)
        if notified is None:
            return []
        window_start = notified.toordinal() - self.policy.velocity_window_days
        recent = [
            prior
            for prior in history.prior_claims
            if (d := _parse_date(prior.notified_date)) is not None
            and window_start <= d.toordinal() <= notified.toordinal()
        ]
        if len(recent) < self.policy.velocity_threshold:
            return []
        kind = RedFlagKind.CLAIMS_VELOCITY
        ids = ",".join(prior.claim_id for prior in recent)
        return [
            RedFlag(
                kind=kind,
                key=signal_key(kind, claim.subject, ids),
                uplift=self.policy.uplift_for(kind),
                reason=(
                    f"{len(recent)} prior claims within {self.policy.velocity_window_days} days, "
                    f"at or above the threshold of {self.policy.velocity_threshold}"
                ),
                citations=(
                    Citation(
                        source_id=f"claims-history:{claim.subject}",
                        title="Claims history",
                        snippet=ids,
                    ),
                ),
            )
        ]

    def _organised_fraud(self, linkage: FraudLinkage) -> list[RedFlag]:
        if not linkage.matched:
            return []
        kind = RedFlagKind.ORGANISED_FRAUD_LINK
        return [
            RedFlag(
                kind=kind,
                key=signal_key(kind, linkage.subject, linkage.ring_ref),
                uplift=self.policy.uplift_for(kind),
                reason=(
                    f"linked to organised-fraud signal {linkage.ring_ref} from the G-series: "
                    f"{linkage.detail}"
                ),
                citations=(
                    Citation(
                        source_id=f"fraud-linkage:{linkage.ring_ref}",
                        title="Organised-fraud linkage (G-series)",
                        snippet=linkage.detail,
                    ),
                ),
            )
        ]
