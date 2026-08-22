"""Canonical synthetic claims, shared by the unit and contract suites.

Every claimant is obviously fictional and every domain is ``.example``. The four fixture claim
ids exercise all four dispositions; a couple of literals (an NRIC planted in a claim file, a
claim id per disposition) give the redaction and routing assertions an independent value to look
for rather than trusting the pipeline to agree with itself.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from claims_integrity_investigator.domain.models import ClaimAssessment

#: The verified principal the tests attribute work to (never a client-asserted actor).
ACTOR = "adjuster@insurer.example"

#: A tenant partition, so the outbound-review assertions are not all on the empty string.
TENANT = "demo-bank"
#: One vocabulary, deliberately. Object-level authorization compares a stored row's data tag
#: against the VERIFIED principal's tenant, and offline that principal is a seeded persona whose
#: tenant is `demo-bank`. A fixture partition spelled differently would be a partition no
#: principal can ever hold, so nothing could be authorized against it and the tag would decorate
#: rather than decide.

#: The four fixture claims, one per disposition (labels are the eval oracle's, not asserted here
#: as behaviour: the engine decides, these are just the ids to drive).
ACCEPT_CLAIM = "CLM-1001"
DECLINE_CLAIM = "CLM-1002"
INVESTIGATE_CLAIM = "CLM-1003"
SIU_CLAIM = "CLM-1004"

#: A claim whose disposition is consequential and therefore always routes (rule R8). Every claim
#: is, so this is simply the SIU one for the routing proofs.
ESCALATING_CLAIM = SIU_CLAIM

#: A planted identifier that lives in a fixture claim file's FNOL free text, so a
#: redaction-before-model assertion has an independent literal to look for rather than trusting
#: the pattern pack to agree with itself. It is Ravi Kumar's synthetic NRIC (see the local
#: fixtures).
PLANTED_NRIC = "S1234567D"
PLANTED_NRIC_CLAIM = ACCEPT_CLAIM

#: A second planted identifier, for the paths the claim file's own redaction cannot reach: a
#: STORED record from another system (the G-series organised-fraud linkage) whose free-text note
#: is quoted into a citation after extraction has already run.
PLANTED_EMAIL = "siu.desk@fictional.example"

#: The fixture claim that matches an organised-fraud ring, so the linkage citation is produced.
RING_CLAIM = "CLM-1004"


def planted_pii_assessment() -> ClaimAssessment:
    """A synthetic escalated assessment carrying a raw NRIC in its summary and a citation.

    The engine's own output never contains PII, so a redaction proof needs a payload with a
    planted identifier to mask. This builds one, so the outbound-review redaction assertion has
    an independent literal to look for.
    """
    from claims_integrity_investigator.domain.kernel import Citation, Decision, Severity
    from claims_integrity_investigator.domain.models import (
        ClaimAssessment,
        CoverageAssessment,
        Recommendation,
        RedFlagAssessment,
    )

    citation = Citation(
        source_id="CLM-9999:fnol",
        title="FNOL",
        snippet=f"claimant NRIC {PLANTED_NRIC} on file",
    )
    return ClaimAssessment(
        claim_id="CLM-9999",
        subject=f"Delta LLP (FICTIONAL), NRIC {PLANTED_NRIC}",
        policy_ref="POL-HOME-999",
        recommendation=Recommendation.SIU_REFER,
        severity=Severity.CRITICAL,
        decision=Decision.ESCALATED,
        coverage=CoverageAssessment(
            policy_ref="POL-HOME-999", lines=(), total_claimed_cents=0, total_indemnity_cents=0
        ),
        red_flags=RedFlagAssessment(flags=(), fraud_score=0.9),
        indemnity_cents=0,
        summary=f"CLM-9999: siu_refer; claimant NRIC {PLANTED_NRIC}",
        narrative="[DRAFT] restated engine figures.",
        requires_human_review=True,
        citations=(citation,),
    )
