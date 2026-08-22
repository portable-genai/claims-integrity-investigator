#!/usr/bin/env python3
"""Evaluation gate for Claims Integrity Investigator (Ins1).

Two named layers via ``--mode`` (the scaffold is ``agent_eval_kit.eval_main``):

* **smoke** (default) - the offline pre-merge check CI runs on every change: it drives the real
  ``ClaimAssessmentService`` against a golden set with SDK-free local adapters and scores every
  metric AGAINST THE DATASET'S OWN oracle, never against the pipeline's own verdict.
* **gate** - the promotion verdict from the shared Hrz4 authority (requires the ``gcp``
  profile), via ``agent_eval_kit.PromotionGateClient``.

Every metric is proved able to go RED before it is trusted (``assert_each_can_go_red``): a metric
that cannot distinguish a wrong answer from a right one, or that reads the pipeline's own answer
instead of the golden oracle, is not a metric. Exit is ``0`` iff every metric meets its threshold
(and, in gate mode, the authority agrees).
"""

from __future__ import annotations

import json
import os
from collections.abc import Iterable, Mapping, Sequence
from pathlib import Path
from typing import Any

from agent_eval_kit import (
    EvalMetricResult,
    EvalReport,
    PromotionGateClient,
    assert_each_can_go_red,
    eval_main,
)
from pii_kit import pack_leak

from claims_integrity_investigator.adapters.local._fixtures import FIXTURE_TENANT
from claims_integrity_investigator.config import (
    Settings,
    build_container,
)
from claims_integrity_investigator.domain.assessment_service import (
    build_assessment_service,
)
from claims_integrity_investigator.domain.models import (
    money,
)
from claims_integrity_investigator.domain.pii import (
    PII_PATTERNS,
)

_REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DATASET = _REPO_ROOT / "eval" / "datasets" / "golden_cases.jsonl"

THRESHOLDS: dict[str, float] = {
    "decision_accuracy": 0.80,
    "quantum_accuracy": 0.99,
    "red_flag_accuracy": 0.80,
    "review_safety": 1.00,
    "groundedness": 0.99,
    "pii_safety": 0.99,
}
#: The registered Hrz4 metric bundle for this vertical (Hrz4 owns the metrics + thresholds).
_BUNDLE = "claims-integrity-investigator"


# --------------------------------------------------------------------------- #
# Pure scorers. Each reads the ORACLE, not the pipeline's verdict, and each is proved able to go
# red below. The input to every scorer is a (predicted, expected) pair drawn from the golden set.
# --------------------------------------------------------------------------- #
def _match(pair: tuple[str, str]) -> float:
    return 1.0 if pair[0] == pair[1] else 0.0


def _quantum(pair: tuple[int, int]) -> float:
    return 1.0 if pair[0] == pair[1] else 0.0


def _flags(pair: tuple[frozenset[str], frozenset[str]]) -> float:
    return 1.0 if pair[0] == pair[1] else 0.0


def _review_safe(flag: bool) -> float:
    return 1.0 if flag else 0.0


def _grounded(pair: tuple[str, tuple[str, str]]) -> float:
    narrative, (indemnity, score) = pair
    return 1.0 if indemnity in narrative and score in narrative else 0.0


def _pii(record: str) -> float:
    return 0.0 if pack_leak(record, PII_PATTERNS) else 1.0


def _prove_metrics_can_go_red() -> None:
    """Wire ``assert_each_can_go_red`` for every metric: a metric that cannot go red is not one."""
    assert_each_can_go_red(
        _match,
        {"right": (("accept", "accept"), ("accept", "decline"))},
        threshold=THRESHOLDS["decision_accuracy"],
        metric="decision_accuracy",
    )
    assert_each_can_go_red(
        _quantum,
        {"exact": ((485000, 485000), (485000, 0))},
        threshold=THRESHOLDS["quantum_accuracy"],
        metric="quantum_accuracy",
    )
    assert_each_can_go_red(
        _flags,
        {
            "set": (
                (frozenset({"staged_loss"}), frozenset({"staged_loss"})),
                (frozenset(), frozenset({"staged_loss"})),
            )
        },
        threshold=THRESHOLDS["red_flag_accuracy"],
        metric="red_flag_accuracy",
    )
    assert_each_can_go_red(
        _review_safe,
        {"human": (True, False)},
        threshold=THRESHOLDS["review_safety"],
        metric="review_safety",
    )
    assert_each_can_go_red(
        _grounded,
        {
            "figures": (
                ("indemnity 485.00 fraud 0.05", ("485.00", "0.05")),
                ("no figures", ("485.00", "0.05")),
            )
        },
        threshold=THRESHOLDS["groundedness"],
        metric="groundedness",
    )
    assert_each_can_go_red(
        _pii,
        {"leak": ("clean summary", "raw NRIC S1234567D leaked")},
        threshold=THRESHOLDS["pii_safety"],
        metric="pii_safety",
    )


def _load(path: Path) -> list[dict[str, object]]:
    cases: list[dict[str, object]] = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        cases.append(json.loads(line))
    if not cases:
        raise SystemExit(f"{path}: golden dataset is empty")
    return cases


def _mean(scores: list[float]) -> float:
    return round(sum(scores) / len(scores), 4) if scores else 0.0


def audit_surfaces(rows: Iterable[Mapping[str, Any]]) -> list[str]:
    """Every CONTENT-bearing field of each persisted audit row, citations included.

    ``redacted_summary`` is one field of several the WORM record keeps, and scoring it alone is
    how a metric ends up certifying the leak it exists to catch: the summary is masked, the
    citations stored beside it in the same row are not, and the identifier survives in a record
    the metric has just called clean. A citation's ``source_id`` is content here, not a bare
    locator, because a locator is built out of the identifiers the case supplied.

    ``actor`` is deliberately absent. It is the VERIFIED principal and an address by design, so a
    blanket scan over a whole row could never go green, and a metric that can never go green is a
    metric somebody switches off. Scanning the content fields is what makes this both sound and
    reachable.
    """
    out: list[str] = []
    for row in rows:
        out.append(str(row.get("redacted_summary", "")))
        out.append(json.dumps(row.get("citations", []), sort_keys=True, default=str))
    return out


def pii_safety(surfaces: Sequence[str], planted: Sequence[str]) -> float:
    """1.0 unless a raw identifier survived into an audit record, by pack row OR by literal.

    The pack scan uses the same rows the redactor masks with, so it catches PII the pipeline
    re-introduced after redaction; the planted-literal scan is an independent oracle that still
    fires when a pack row is narrowed or broken (the two-part scorer lesson from the C4 rollout).
    """
    pack_leaked = any(pack_leak(text, PII_PATTERNS) for text in surfaces)
    literal_leaked = any(token in text for token in planted for text in surfaces)
    return 0.0 if (pack_leaked or literal_leaked) else 1.0


def run_smoke(dataset: Path) -> EvalReport:
    _prove_metrics_can_go_red()
    cases = _load(dataset)
    container = build_container(Settings(profile="local", audit_path=":memory:"))
    service = build_assessment_service(container)

    decision: list[float] = []
    quantum: list[float] = []
    red_flag: list[float] = []
    review_safety: list[float] = []
    groundedness: list[float] = []
    for case in cases:
        result = service.assess(str(case["claim_id"]), actor="eval-bot", tenant=FIXTURE_TENANT)
        decision.append(_match((result.recommendation.value, str(case["expected_recommendation"]))))
        quantum.append(_quantum((result.indemnity_cents, int(case["expected_indemnity_cents"]))))  # type: ignore[arg-type]
        detected = frozenset(flag.kind.value for flag in result.red_flags.flags)
        expected = frozenset(str(k) for k in case["expected_flags"])  # type: ignore[union-attr]
        red_flag.append(_flags((detected, expected)))
        review_safety.append(_review_safe(result.requires_human_review))
        groundedness.append(
            _grounded(
                (
                    result.narrative,
                    (money(result.indemnity_cents), str(result.red_flags.fraud_score)),
                )
            )
        )

    # pii_safety: no raw identifier may survive into any audit record.
    surfaces = audit_surfaces(container.audit.log.read_all())
    planted = [str(case["planted"]) for case in cases if case.get("planted")]

    results = (
        EvalMetricResult.scored(
            "decision_accuracy", _mean(decision), THRESHOLDS["decision_accuracy"]
        ),
        EvalMetricResult.scored("quantum_accuracy", _mean(quantum), THRESHOLDS["quantum_accuracy"]),
        EvalMetricResult.scored(
            "red_flag_accuracy", _mean(red_flag), THRESHOLDS["red_flag_accuracy"]
        ),
        EvalMetricResult.scored("review_safety", _mean(review_safety), THRESHOLDS["review_safety"]),
        EvalMetricResult.scored("groundedness", _mean(groundedness), THRESHOLDS["groundedness"]),
        EvalMetricResult.scored(
            "pii_safety", pii_safety(surfaces, planted), THRESHOLDS["pii_safety"]
        ),
    )
    return EvalReport(dataset=str(dataset), results=results, n_examples=len(cases))


def run_gate(dataset: Path) -> tuple[EvalReport, bool]:
    settings = Settings.load()
    if settings.profile != "gcp":
        raise SystemExit(
            "--mode gate is the promotion authority and requires "
            f"CLAIMSINTEG_PROFILE=gcp (got {settings.profile!r}); "
            "run --mode smoke for the offline pre-merge check."
        )
    client = PromotionGateClient(
        os.environ.get("CLAIMSINTEG_QUALITY_URL", "http://localhost:8084"),
        bundle=_BUNDLE,
        model="gemini-3.5-flash",
    )
    return client.evaluate(str(dataset)), client.gate(str(dataset))


if __name__ == "__main__":
    raise SystemExit(
        eval_main(
            smoke=run_smoke,
            gate=run_gate,
            default_dataset=DEFAULT_DATASET,
            description="Offline / Hrz4 evaluation gate for Ins1.",
        )
    )
