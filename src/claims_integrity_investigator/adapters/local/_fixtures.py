"""Deterministic, obviously fictional claim fixtures for the offline profile.

Every claimant is plainly invented, every identifier is synthetic and every domain is
``.example``. The claim documents carry a compact marker grammar (``META`` / ``SCHED`` / ``LINE``
lines) that the local extractor parses, alongside free-text FNOL and adjuster prose that carries
the (synthetic) PII the redaction step masks and the staged-loss markers the red-flag engine
scans. The four claims are chosen to exercise all four dispositions; the eval's golden oracle
labels them independently, so this file is never the source of the expected outcome.
"""

from __future__ import annotations

from ...domain.kernel import Citation
from ...domain.models import (
    ClaimsHistory,
    DocumentKind,
    FraudLinkage,
    PriorClaim,
    RawClaimFile,
    RawDocument,
    RetrievedPassage,
)

# --------------------------------------------------------------------------- #
# Claim files (marker grammar + free text)
# --------------------------------------------------------------------------- #
#: The tenant every fixture claim file belongs to. It matches the seeded personas' tenant,
#: because object-level authorization compares a row's data tag against the VERIFIED principal,
#: and the seeded personas are what the offline profile verifies. It is not `Settings.tenant`,
#: which is the partition asserted on an OUTBOUND review.
FIXTURE_TENANT = "demo-bank"

_CLEAN_FNOL = (
    "FNOL: claimant Ravi Kumar (FICTIONAL), NRIC S1234567D, ops@ravi.example, reports water "
    "damage to home contents after a burst pipe. Cooperative, documents provided.\n"
    "META loss=2026-03-01 notified=2026-03-05"
)
_CLEAN_SCHEDULE = (
    "POLICY SCHEDULE POL-HOME-001\n"
    "SCHED category=contents included=true excess=25000 sublimit=800000 exclusion=\n"
    "SCHED category=temporary_accommodation included=true excess=0 sublimit=300000 exclusion="
)
_CLEAN_INVOICES = (
    "INVOICES\n"
    "LINE id=L1 category=contents desc=water-damaged sofa and rug cents=420000 "
    "invoice=INV-7781 date=2026-03-04 doc=inv:INV-7781\n"
    "LINE id=L2 category=temporary_accommodation desc=three nights hotel cents=90000 "
    "invoice=INV-7782 date=2026-03-06 doc=inv:INV-7782"
)

_FLOOD_FNOL = (
    "FNOL: claimant Mei Ling (FICTIONAL), NRIC S7654321A, mei@lianghome.example, reports flood "
    "damage from a river overflow to ground-floor contents.\n"
    "META loss=2026-04-10 notified=2026-04-12"
)
_FLOOD_SCHEDULE = (
    "POLICY SCHEDULE POL-HOME-014\n"
    "SCHED category=contents included=false excess=25000 sublimit= exclusion=EXC-FLOOD-3\n"
    "SCHED category=contents_storm included=true excess=25000 sublimit=800000 exclusion="
)
_FLOOD_INVOICES = (
    "INVOICES\n"
    "LINE id=L1 category=contents desc=flood-damaged flooring cents=650000 "
    "invoice=INV-3300 date=2026-04-13 doc=inv:INV-3300"
)

_STAGED_FNOL = (
    "FNOL: claimant Jordan Blake (FICTIONAL), NRIC S2223334B, jordan@blakeauto.example, reports "
    "theft of tools from a locked van.\n"
    "META loss=2026-01-02 notified=2026-03-20"
)
_STAGED_ADJUSTER = (
    "ADJUSTER NOTE: attended site. No forced entry to the van was evident. Claimant "
    "cooperative; storage location confirmed."
)
_STAGED_SCHEDULE = (
    "POLICY SCHEDULE POL-MOTOR-052\n"
    "SCHED category=tools included=true excess=20000 sublimit=500000 exclusion="
)
_STAGED_INVOICES = (
    "INVOICES\n"
    "LINE id=L1 category=tools desc=replacement power tools cents=287500 "
    "invoice=INV-9001 date=2026-03-18 doc=inv:INV-9001\n"
    "LINE id=L2 category=tools desc=tool chest cents=96300 "
    "invoice=INV-9002 date=2026-03-18 doc=inv:INV-9002"
)

_RING_FNOL = (
    "FNOL: claimant Priya Nair (FICTIONAL), NRIC S9998887C, priya@nairclinic.example, reports a "
    "motor collision with third-party injury.\n"
    "META loss=2026-05-01 notified=2026-05-03"
)
_RING_SCHEDULE = (
    "POLICY SCHEDULE POL-MOTOR-088\n"
    "SCHED category=motor_repair included=true excess=50000 sublimit=1500000 exclusion=\n"
    "SCHED category=personal_injury included=true excess=0 sublimit=2000000 exclusion="
)
_RING_INVOICES = (
    "INVOICES\n"
    "LINE id=L1 category=motor_repair desc=panel and chassis repair cents=1200000 "
    "invoice=INV-5501 date=2026-05-06 doc=inv:INV-5501\n"
    "LINE id=L2 category=personal_injury desc=physiotherapy course cents=800000 "
    "invoice=INV-5502 date=2026-05-07 doc=inv:INV-5502"
)


def _claim(
    claim_id: str,
    subject: str,
    policy_ref: str,
    fnol: str,
    schedule: str,
    invoices: str,
    adjuster: str = "",
) -> RawClaimFile:
    documents = [
        RawDocument(doc_ref=f"{claim_id}:fnol", kind=DocumentKind.FNOL, text=fnol),
        RawDocument(
            doc_ref=f"{claim_id}:schedule", kind=DocumentKind.POLICY_SCHEDULE, text=schedule
        ),
        RawDocument(doc_ref=f"{claim_id}:invoices", kind=DocumentKind.INVOICE, text=invoices),
    ]
    if adjuster:
        documents.append(
            RawDocument(
                doc_ref=f"{claim_id}:adjuster", kind=DocumentKind.ADJUSTER_NOTE, text=adjuster
            )
        )
    return RawClaimFile(
        claim_id=claim_id,
        subject=subject,
        policy_ref=policy_ref,
        documents=tuple(documents),
        tenant=FIXTURE_TENANT,
    )


CLAIM_FILES: dict[str, RawClaimFile] = {
    "CLM-1001": _claim(
        "CLM-1001",
        "Ravi Kumar (FICTIONAL)",
        "POL-HOME-001",
        _CLEAN_FNOL,
        _CLEAN_SCHEDULE,
        _CLEAN_INVOICES,
    ),
    "CLM-1002": _claim(
        "CLM-1002",
        "Mei Ling (FICTIONAL)",
        "POL-HOME-014",
        _FLOOD_FNOL,
        _FLOOD_SCHEDULE,
        _FLOOD_INVOICES,
    ),
    "CLM-1003": _claim(
        "CLM-1003",
        "Jordan Blake (FICTIONAL)",
        "POL-MOTOR-052",
        _STAGED_FNOL,
        _STAGED_SCHEDULE,
        _STAGED_INVOICES,
        adjuster=_STAGED_ADJUSTER,
    ),
    "CLM-1004": _claim(
        "CLM-1004",
        "Priya Nair (FICTIONAL)",
        "POL-MOTOR-088",
        _RING_FNOL,
        _RING_SCHEDULE,
        _RING_INVOICES,
    ),
}


# --------------------------------------------------------------------------- #
# Policy-wording corpus (what the governed-RAG / Hrz2 local stand-in returns)
# --------------------------------------------------------------------------- #
def _passage(clause: str, policy_ref: str, title: str, text: str, score: float) -> RetrievedPassage:
    return RetrievedPassage(
        text=text,
        citation=Citation(source_id=clause, title=title, snippet=text[:120]),
        score=score,
    )


# Keyed by policy_ref: the wording passages a query filtered to that policy returns.
POLICY_CORPUS: dict[str, tuple[RetrievedPassage, ...]] = {
    "POL-HOME-001": (
        _passage(
            "CL-CONTENTS-1",
            "POL-HOME-001",
            "Home contents cover",
            "Section 2: home contents are covered for accidental and escape-of-water damage, "
            "subject to the schedule excess and sub-limit.",
            0.94,
        ),
        _passage(
            "CL-ALT-ACCOM-2",
            "POL-HOME-001",
            "Temporary accommodation",
            "Section 4: reasonable temporary accommodation is payable while the home is "
            "uninhabitable, up to the schedule sub-limit.",
            0.90,
        ),
    ),
    "POL-HOME-014": (
        _passage(
            "EXC-FLOOD-3",
            "POL-HOME-014",
            "Flood exclusion",
            "Exclusion 3: loss or damage caused by flood, including river overflow, is excluded "
            "unless the storm-and-flood extension was purchased.",
            0.96,
        ),
    ),
    "POL-MOTOR-052": (
        _passage(
            "CL-TOOLS-1",
            "POL-MOTOR-052",
            "Tools in a vehicle",
            "Section 6: tools left in a locked vehicle are covered against theft following "
            "forcible and violent entry, subject to the excess and sub-limit.",
            0.93,
        ),
    ),
    "POL-MOTOR-088": (
        _passage(
            "CL-MOTOR-1",
            "POL-MOTOR-088",
            "Motor repair cover",
            "Section 1: accidental damage to the insured vehicle is covered up to the schedule "
            "sub-limit, less the excess.",
            0.92,
        ),
        _passage(
            "CL-INJURY-2",
            "POL-MOTOR-088",
            "Personal injury cover",
            "Section 3: third-party and occupant injury treatment is payable up to the schedule "
            "sub-limit.",
            0.91,
        ),
    ),
}


# --------------------------------------------------------------------------- #
# Claims history and organised-fraud linkage
# --------------------------------------------------------------------------- #
CLAIMS_HISTORY: dict[str, ClaimsHistory] = {
    # Two priors in the window: below the velocity threshold, so this claimant's velocity rule
    # does not fire. The velocity rule's provable-red coverage lives in the engine unit tests,
    # which construct a claimant at and above the threshold directly.
    "Jordan Blake (FICTIONAL)": ClaimsHistory(
        subject="Jordan Blake (FICTIONAL)",
        prior_claims=(
            PriorClaim(claim_id="CLM-0801", notified_date="2025-06-10", paid_cents=150000),
            PriorClaim(claim_id="CLM-0844", notified_date="2025-09-22", paid_cents=90000),
        ),
    ),
}

FRAUD_LINKAGE: dict[str, FraudLinkage] = {
    "Priya Nair (FICTIONAL)": FraudLinkage(
        subject="Priya Nair (FICTIONAL)",
        matched=True,
        ring_ref="RING-DELTA-7",
        detail="clinic and repairer both flagged in a staged-collision ring by the G-series",
    ),
}


def claims_history_for(subject: str) -> ClaimsHistory:
    return CLAIMS_HISTORY.get(subject, ClaimsHistory(subject=subject, prior_claims=()))


def fraud_linkage_for(subject: str) -> FraudLinkage:
    return FRAUD_LINKAGE.get(subject, FraudLinkage(subject=subject, matched=False))
