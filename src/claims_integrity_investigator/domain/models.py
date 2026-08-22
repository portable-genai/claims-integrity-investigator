"""Vertical artifact models: the claim, the extracted evidence, and the assessment.

The artifacts THIS vertical produces, as opposed to the vertical-neutral machinery in
``kernel.py``. The service's own name is deliberately not substituted into this docstring: a
rendered line whose length depends on ``friendly_name`` fails the repo's own format check for
no reason but the length of its name.

Money is carried as integer CENTS everywhere a figure is consequential: a float indemnity is a
rounding bug waiting to be cited as a fact. Every dataclass is frozen, so an artifact a caller
holds cannot be mutated after the engine computed and cited it.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from hex_service_kit.enums import LenientStrEnum

from .kernel import Citation, Decision, Severity


class Recommendation(LenientStrEnum):
    """The disposition the deterministic engine recommends. All four are human-approved."""

    ACCEPT = "accept"
    INVESTIGATE = "investigate"
    DECLINE = "decline"
    SIU_REFER = "siu_refer"


class CoverStatus(LenientStrEnum):
    """The per-line coverage verdict the deterministic engine assigns."""

    IN_COVER = "in_cover"
    EXCLUDED = "excluded"
    SUB_LIMIT = "sub_limit"
    EXCESS = "excess"
    #: The policy wording needed to decide this line was not retrieved; the engine refuses to
    #: guess and pays nothing pending the wording (see ``coverage_engine``).
    NO_BASIS = "no_basis"


class RedFlagKind(LenientStrEnum):
    """The fraud-indicator families the deterministic red-flag engine can raise."""

    LATE_NOTIFICATION = "late_notification"
    STAGED_LOSS = "staged_loss"
    INVOICE_ANOMALY = "invoice_anomaly"
    CLAIMS_VELOCITY = "claims_velocity"
    ORGANISED_FRAUD_LINK = "organised_fraud_link"


class DocumentKind(LenientStrEnum):
    """The kinds of document a claim file carries (drives the local deterministic parser)."""

    FNOL = "fnol"
    ADJUSTER_NOTE = "adjuster_note"
    INVOICE = "invoice"
    POLICY_SCHEDULE = "policy_schedule"
    MEDICAL_REPORT = "medical_report"
    REPAIR_REPORT = "repair_report"
    PHOTO = "photo"


# --------------------------------------------------------------------------- #
# Raw intake (what the claim-file port returns; it computes nothing)
# --------------------------------------------------------------------------- #
@dataclass(frozen=True, slots=True)
class RawDocument:
    """One document in a claim file, as fetched: a kind, its text and a stable locator."""

    doc_ref: str
    kind: DocumentKind
    text: str


@dataclass(frozen=True, slots=True)
class RawClaimFile:
    """A claim file as the source system holds it: raw documents plus the keys to cite them."""

    claim_id: str
    subject: str
    policy_ref: str
    documents: tuple[RawDocument, ...] = ()
    #: The tenant that OWNS this file: the data tag object-level authorization is derived from.
    #: A claim id is a name, not an entitlement, so the port matches this against the verified
    #: principal's tenant and refuses anything else. Empty means the row predates tagging and
    #: belongs to nobody, so no principal may read it.
    tenant: str = ""


# --------------------------------------------------------------------------- #
# Extracted evidence (what the extraction port produces; it decides nothing)
# --------------------------------------------------------------------------- #
@dataclass(frozen=True, slots=True)
class ClaimLine:
    """One claimed item: a category, an amount in cents, and its invoice provenance."""

    line_id: str
    category: str
    description: str
    claimed_cents: int
    doc_ref: str
    invoice_no: str = ""
    invoice_date: str = ""  # ISO date, "" when the document carried none


@dataclass(frozen=True, slots=True)
class PolicyItem:
    """One line of the policy schedule: whether a category is covered and on what terms."""

    category: str
    included: bool
    excess_cents: int = 0
    sub_limit_cents: int | None = None
    exclusion_clause: str = ""  # the clause id the wording must be retrieved for


@dataclass(frozen=True, slots=True)
class ExtractedClaim:
    """The structured evidence the engines reason over. Extraction gathers it; it decides none."""

    claim_id: str
    subject: str
    policy_ref: str
    loss_date: str  # ISO date
    notified_date: str  # ISO date
    lines: tuple[ClaimLine, ...] = ()
    schedule: tuple[PolicyItem, ...] = ()
    adjuster_notes: str = ""


# --------------------------------------------------------------------------- #
# Governed policy-wording retrieval (Hrz2 RetrievalPort shape)
# --------------------------------------------------------------------------- #
@dataclass(frozen=True, slots=True)
class RetrievalQuery:
    """A query for policy wording, resolved by the governed-RAG adapter (Hrz2)."""

    text: str
    top_k: int = 8
    filters: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class RetrievedPassage:
    """One retrieved policy-wording passage with a clause-level citation."""

    text: str
    citation: Citation
    score: float = 0.0


# --------------------------------------------------------------------------- #
# Claims history and organised-fraud linkage (external signals; ports return them raw)
# --------------------------------------------------------------------------- #
@dataclass(frozen=True, slots=True)
class PriorClaim:
    """One prior claim for the same claimant, from the claims-history store."""

    claim_id: str
    notified_date: str  # ISO date
    paid_cents: int = 0


@dataclass(frozen=True, slots=True)
class ClaimsHistory:
    """The claimant's prior-claims record the velocity rule reads (it computes nothing here)."""

    subject: str
    prior_claims: tuple[PriorClaim, ...] = ()


@dataclass(frozen=True, slots=True)
class FraudLinkage:
    """Organised-fraud signals for a claimant, arriving from the G-series suite as a data feed."""

    subject: str
    matched: bool = False
    ring_ref: str = ""
    detail: str = ""


# --------------------------------------------------------------------------- #
# Engine outputs
# --------------------------------------------------------------------------- #
@dataclass(frozen=True, slots=True)
class CoverageLine:
    """The coverage verdict for one claim line: a status, an indemnity, and cited reasoning."""

    line_id: str
    category: str
    claimed_cents: int
    status: CoverStatus
    indemnity_cents: int
    reason: str
    citations: tuple[Citation, ...] = ()


@dataclass(frozen=True, slots=True)
class CoverageAssessment:
    """The whole-claim coverage result: per-line verdicts and the summed indemnity quantum."""

    policy_ref: str
    lines: tuple[CoverageLine, ...]
    total_claimed_cents: int
    total_indemnity_cents: int


@dataclass(frozen=True, slots=True)
class RedFlag:
    """One fraud indicator: a kind, a stable fingerprint, a score uplift and cited reasoning."""

    kind: RedFlagKind
    key: str
    uplift: float
    reason: str
    citations: tuple[Citation, ...] = ()


@dataclass(frozen=True, slots=True)
class RedFlagAssessment:
    """The fraud-indicator result: the raised flags and the clamped fraud score."""

    flags: tuple[RedFlag, ...]
    fraud_score: float


# --------------------------------------------------------------------------- #
# The assessment the service produces (the artifact that escalates and is audited)
# --------------------------------------------------------------------------- #
@dataclass(frozen=True, slots=True)
class ClaimAssessment:
    """The claim disposition: engine coverage and fraud findings plus a cited, drafted narrative.

    Every one of the four recommendations is consequential and human-approved, so
    ``requires_human_review`` is always True and the surfaces route it to Hrz7 (rule R8). The
    ``severity`` and ``decision`` fields exist so this artifact flows through the same audit and
    review-router machinery the template ships; ``summary`` is the one-line, figure-bearing
    headline the audit record and the review payload carry.
    """

    claim_id: str
    subject: str
    policy_ref: str
    recommendation: Recommendation
    severity: Severity
    decision: Decision
    coverage: CoverageAssessment
    red_flags: RedFlagAssessment
    indemnity_cents: int
    summary: str
    narrative: str
    requires_human_review: bool
    citations: tuple[Citation, ...] = ()

    @property
    def indemnity(self) -> str:
        """The indemnity quantum rendered as a currency amount for display and citation."""
        return money(self.indemnity_cents)


def money(cents: int) -> str:
    """Render an integer cent amount as a fixed-point currency string (never a float)."""
    sign = "-" if cents < 0 else ""
    whole, frac = divmod(abs(cents), 100)
    return f"{sign}{whole:,}.{frac:02d}"


# --------------------------------------------------------------------------- #
# Generation (the LLM's narrow job: draft the cited narrative, never a figure)
# --------------------------------------------------------------------------- #
@dataclass(frozen=True, slots=True)
class LlmMessage:
    """One turn handed to the generation port."""

    role: str  # "user" | "model"
    content: str


@dataclass(frozen=True, slots=True)
class LlmRequest:
    """A structured-output generation request. The model narrates; it computes nothing."""

    messages: tuple[LlmMessage, ...]
    system_instruction: str = ""
    model: str | None = None
    temperature: float = 0.2
    max_output_tokens: int = 2048
    response_schema: dict[str, object] | None = None


@dataclass(frozen=True, slots=True)
class LlmResponse:
    """A generation response. ``text`` is the structured JSON when a schema was requested."""

    text: str
    model: str = ""
