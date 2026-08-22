"""The deterministic coverage/indemnity engine: quantum exactness and the refusal rule.

The consequential figures are pure arithmetic, so they are hand-computed here as an independent
oracle rather than read back from the engine. The refuse-when-no-wording rule (slice 2) is the
one that stops a coverage decision from being made with no clause behind it, so it carries a
red-before/green-after proof.
"""

from __future__ import annotations

from claims_integrity_investigator.domain.coverage_engine import CoverageEngine
from claims_integrity_investigator.domain.kernel import Citation
from claims_integrity_investigator.domain.models import (
    ClaimLine,
    CoverStatus,
    ExtractedClaim,
    PolicyItem,
    RetrievedPassage,
)


def _passage(clause: str) -> RetrievedPassage:
    return RetrievedPassage(
        text=f"wording for {clause}",
        citation=Citation(source_id=clause, title=clause, snippet="s"),
        score=0.9,
    )


def _claim(lines: tuple[ClaimLine, ...], schedule: tuple[PolicyItem, ...]) -> ExtractedClaim:
    return ExtractedClaim(
        claim_id="CLM-T",
        subject="Test Claimant (FICTIONAL)",
        policy_ref="POL-T",
        loss_date="2026-01-01",
        notified_date="2026-01-05",
        lines=lines,
        schedule=schedule,
    )


def test_in_cover_line_pays_claimed_less_excess() -> None:
    claim = _claim(
        (ClaimLine("L1", "contents", "sofa", 420_000, "inv:1"),),
        (PolicyItem("contents", included=True, excess_cents=25_000, sub_limit_cents=800_000),),
    )
    result = CoverageEngine().assess(claim, (_passage("CL-1"),))
    line = result.lines[0]
    # Oracle: 420000 - 25000 excess = 395000, and the excess bound the payout.
    assert line.indemnity_cents == 395_000
    assert line.status is CoverStatus.EXCESS
    assert result.total_indemnity_cents == 395_000


def test_sub_limit_caps_before_excess() -> None:
    claim = _claim(
        (ClaimLine("L1", "contents", "jewellery", 900_000, "inv:1"),),
        (PolicyItem("contents", included=True, excess_cents=25_000, sub_limit_cents=500_000),),
    )
    line = CoverageEngine().assess(claim, (_passage("CL-1"),)).lines[0]
    # Oracle: capped to 500000 sub-limit, then less 25000 excess = 475000.
    assert line.indemnity_cents == 475_000
    assert line.status is CoverStatus.SUB_LIMIT


def test_excluded_line_pays_nothing_and_cites_the_clause() -> None:
    claim = _claim(
        (ClaimLine("L1", "contents", "flood damage", 650_000, "inv:1"),),
        (PolicyItem("contents", included=False, exclusion_clause="EXC-FLOOD-3"),),
    )
    line = CoverageEngine().assess(claim, (_passage("EXC-FLOOD-3"),)).lines[0]
    assert line.indemnity_cents == 0
    assert line.status is CoverStatus.EXCLUDED
    assert any(c.source_id == "EXC-FLOOD-3" for c in line.citations)


def test_the_engine_refuses_rather_than_guesses_when_no_wording_is_retrieved() -> None:
    """Slice 2's rule: with no policy wording, cover cannot be confirmed and nothing is paid.

    Red-before/green-after in one test: the SAME claim with wording pays out (green) and with no
    wording pays nothing and marks NO_BASIS (the refusal).
    """
    claim = _claim(
        (ClaimLine("L1", "contents", "sofa", 420_000, "inv:1"),),
        (PolicyItem("contents", included=True, excess_cents=25_000, sub_limit_cents=800_000),),
    )
    with_wording = CoverageEngine().assess(claim, (_passage("CL-1"),))
    assert with_wording.total_indemnity_cents == 395_000

    without_wording = CoverageEngine().assess(claim, ())
    assert without_wording.total_indemnity_cents == 0
    assert all(line.status is CoverStatus.NO_BASIS for line in without_wording.lines)


def test_a_category_absent_from_the_schedule_has_no_basis() -> None:
    claim = _claim(
        (ClaimLine("L1", "cyber", "ransom", 100_000, "inv:1"),),
        (PolicyItem("contents", included=True, excess_cents=0),),
    )
    line = CoverageEngine().assess(claim, (_passage("CL-1"),)).lines[0]
    assert line.status is CoverStatus.NO_BASIS
    assert line.indemnity_cents == 0
