"""The deterministic coverage and indemnity engine: pure, replayable, cited to a clause.

The consequential coverage decision (per-line status and the indemnity quantum) is pure stdlib
arithmetic over the extracted claim and the policy schedule; an LLM produces none of it. Every
figure is cited to a policy clause (from the retrieved wording) and to the claimed invoice line,
so a human reviewer can trace each cent.

The refusal rule is the point of slice 2: when the policy WORDING that governs a line was not
retrieved (the corpus was empty, or the governed-RAG port returned nothing for the clause), the
engine does not guess. It marks the line :data:`CoverStatus.NO_BASIS`, pays nothing, and lets
the disposition escalate. Guessing cover from an excluded-or-not flag with no wording behind it
is exactly the unprovenanced decision the citation rule exists to prevent.
"""

from __future__ import annotations

from dataclasses import dataclass

from .kernel import Citation
from .models import (
    ClaimLine,
    CoverageAssessment,
    CoverageLine,
    CoverStatus,
    ExtractedClaim,
    PolicyItem,
    RetrievedPassage,
    money,
)


@dataclass(frozen=True, slots=True)
class CoverageEngine:
    """Pure per-line coverage verdicts and the summed indemnity quantum."""

    def assess(
        self,
        claim: ExtractedClaim,
        passages: tuple[RetrievedPassage, ...],
    ) -> CoverageAssessment:
        """Return per-line coverage verdicts and the total indemnity, every figure cited.

        ``passages`` is the retrieved policy wording. It is the WITNESS that the schedule can be
        trusted: with none retrieved the engine has no clause text to stand a verdict on, so
        every line is :data:`CoverStatus.NO_BASIS` and the quantum is zero pending the wording.
        """
        by_category = {item.category: item for item in claim.schedule}
        clause_citations = _clause_index(passages)
        lines = tuple(
            self._line(line, by_category.get(line.category), passages, clause_citations)
            for line in claim.lines
        )
        total_claimed = sum(line.claimed_cents for line in claim.lines)
        total_indemnity = sum(line.indemnity_cents for line in lines)
        return CoverageAssessment(
            policy_ref=claim.policy_ref,
            lines=lines,
            total_claimed_cents=total_claimed,
            total_indemnity_cents=total_indemnity,
        )

    def _line(
        self,
        line: ClaimLine,
        item: PolicyItem | None,
        passages: tuple[RetrievedPassage, ...],
        clause_citations: dict[str, Citation],
    ) -> CoverageLine:
        line_citation = Citation(
            source_id=line.doc_ref,
            title=f"Claim line {line.line_id}",
            snippet=f"{line.description} ({money(line.claimed_cents)})",
        )
        # No wording retrieved at all: the engine refuses to decide any line rather than guess.
        if not passages:
            return CoverageLine(
                line_id=line.line_id,
                category=line.category,
                claimed_cents=line.claimed_cents,
                status=CoverStatus.NO_BASIS,
                indemnity_cents=0,
                reason=(
                    "policy wording was not retrieved; cover cannot be confirmed and nothing "
                    "is paid pending the wording"
                ),
                citations=(line_citation,),
            )
        if item is None:
            return CoverageLine(
                line_id=line.line_id,
                category=line.category,
                claimed_cents=line.claimed_cents,
                status=CoverStatus.NO_BASIS,
                indemnity_cents=0,
                reason=f"category {line.category!r} is absent from the policy schedule",
                citations=(line_citation,),
            )
        if not item.included:
            cites = (line_citation, *_exclusion_cites(item, clause_citations))
            return CoverageLine(
                line_id=line.line_id,
                category=line.category,
                claimed_cents=line.claimed_cents,
                status=CoverStatus.EXCLUDED,
                indemnity_cents=0,
                reason=_excluded_reason(item),
                citations=cites,
            )
        return self._payable(line, item, line_citation, clause_citations)

    def _payable(
        self,
        line: ClaimLine,
        item: PolicyItem,
        line_citation: Citation,
        clause_citations: dict[str, Citation],
    ) -> CoverageLine:
        """Apply the sub-limit cap then the excess; the status names the binding constraint."""
        amount = line.claimed_cents
        status = CoverStatus.IN_COVER
        reasons: list[str] = []
        if item.sub_limit_cents is not None and amount > item.sub_limit_cents:
            amount = item.sub_limit_cents
            status = CoverStatus.SUB_LIMIT
            reasons.append(
                f"capped at the {money(item.sub_limit_cents)} sub-limit for {item.category}"
            )
        if item.excess_cents:
            amount = max(0, amount - item.excess_cents)
            if status is CoverStatus.IN_COVER:
                status = CoverStatus.EXCESS
            reasons.append(f"less the {money(item.excess_cents)} policy excess")
        if not reasons:
            reasons.append(f"in cover for {item.category}, paid in full")
        cites = (line_citation, *_exclusion_cites(item, clause_citations))
        return CoverageLine(
            line_id=line.line_id,
            category=line.category,
            claimed_cents=line.claimed_cents,
            status=status,
            indemnity_cents=amount,
            reason="; ".join(reasons),
            citations=cites,
        )


def _clause_index(passages: tuple[RetrievedPassage, ...]) -> dict[str, Citation]:
    """Map a clause id (the citation ``source_id``) to its retrieved citation, first wins."""
    index: dict[str, Citation] = {}
    for passage in passages:
        index.setdefault(passage.citation.source_id, passage.citation)
    return index


def _exclusion_cites(
    item: PolicyItem, clause_citations: dict[str, Citation]
) -> tuple[Citation, ...]:
    if item.exclusion_clause and item.exclusion_clause in clause_citations:
        return (clause_citations[item.exclusion_clause],)
    return ()


def _excluded_reason(item: PolicyItem) -> str:
    if item.exclusion_clause:
        return f"excluded under clause {item.exclusion_clause}; nothing is payable"
    return f"category {item.category} is not covered by the policy; nothing is payable"
