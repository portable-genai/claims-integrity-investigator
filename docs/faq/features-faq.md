# Features FAQ

For claims, SIU, product and delivery teams: what this agent produces, what is deterministic vs
what the model does, and, importantly, where Ins1's responsibilities **stop** and a sibling
catalog system takes over. Cross-references: [`../../README.md`](../../README.md),
[`../../DEMO.md`](../../DEMO.md), [`../../ARCHITECTURE.md`](../../ARCHITECTURE.md).

### What does Ins1 actually produce?

A cited **claim assessment**. From one claim id it fetches the claim file (FNOL, adjuster notes,
invoices, the policy schedule), extracts structured evidence, retrieves the governing policy
wording, and produces four things:

- **per-line coverage verdicts** with a status naming the binding constraint (`in_cover`,
  `sub_limit`, `excess`, `excluded`, `no_basis`) and a reason;
- **an indemnity quantum** in integer cents, summed from the covered lines after the sub-limit
  cap and then the policy excess;
- **fraud indicators**, each a fingerprinted `RedFlag` with its own uplift and cited evidence,
  plus a clamped fraud score;
- **a recommendation**: accept, investigate, decline or SIU-refer.

Every figure carries a `Citation` back to the invoice line, the claim document or the policy
clause it came from, and the whole assessment is written to a tamper-evident audit trail.

### What is deterministic vs done by the LLM?

The consequential work is **pure stdlib, deterministic and unit-tested**. The coverage verdicts
and the indemnity quantum come from `domain/coverage_engine.py:CoverageEngine`; the indicators
and the score come from `domain/red_flags.py:RedFlagEngine`; the disposition comes from the
short pure `recommend()` function in `domain/assessment_service.py`, which reads its thresholds
off the injected policy (an organised-fraud link refers to SIU regardless of score, then the
bands apply, then no cover declines, else accept).

The model has exactly one job, in `domain/drafting.py:AssessmentDrafter`: draft a three-to-four
sentence narrative that RESTATES the figures it is handed. Its system instruction says so, its
output is JSON validated against a schema and DISCARDED on failure in favour of a deterministic
template, and the recommendation is passed to it as "Recommendation (fixed)". A model change
cannot move a figure, and
`tests/unit/test_assessment_service.py::test_the_numbers_are_identical_whatever_the_generator_returns`
is the proof. See [`../model-card.md`](../model-card.md) for the full boundary.

One deliberate refusal is worth knowing about: when no policy wording was retrieved, the
coverage engine does not guess. Every line becomes `no_basis`, the quantum is zero pending the
wording, and the disposition escalates. Guessing cover from a schedule flag with no clause text
behind it is exactly the unprovenanced decision the citation rule exists to prevent
(`tests/unit/test_coverage_engine.py::test_the_engine_refuses_rather_than_guesses_when_no_wording_is_retrieved`).

### Is anything auto-approved? Does it pay a claim?

No, and no. **Every** assessment sets `requires_human_review=True` and carries
`Decision.ESCALATED`, including the clean accept case, and every surface routes it to the
**Hrz7** Human-Review and Maker-Checker Console in the same call that produced it (rule R8): the
API (`POST /v1/assess`), the CLI (`assess`) and the agent tool (`assess_claim`) all call
`ReviewRouterPort.route` before returning, and the response carries a `review_ref` so a caller
can tell a routed escalation from one that stopped locally. An SIU-refer maps to CRITICAL, which
demands dual control (two approvals) in the outbound payload. The agent proposes; a human
disposes; a downstream system pays.

### What is the personal-data position?

Unlike most catalog systems, this one genuinely handles claimant personal data, so it redacts
rather than declaring the control not applicable. Masking happens before the extraction model
sees the file, before the audit write, before the review payload leaves the process, and over
every string of an agent tool result. `domain/pii.py:JURISDICTIONS` selects which `pii-kit`
rows apply (SG, HK, JP, AU by default) in an order this vertical owns; the outbound review
payload is scrubbed against every jurisdiction's rows regardless, because the console is a
shared sink. See [security-faq.md](security-faq.md) and [compliance-faq.md](compliance-faq.md).

### Which capabilities does this repo own vs integrate from the catalog?

Ins1 **owns** the claim-assessment domain logic and its outputs. It **integrates** several
cross-cutting concerns owned by sibling systems. Do not rebuild these in a fork:

| Concern | Owned by (catalog id / repo) | Ins1's role |
|---|---|---|
| Governed RAG over the insurer's policy wordings, with ACLs and citations | **Hrz2** `enterprise-knowledge-base` | a HARD dependency: retrieval goes through the Hrz2 governed-RAG service (`ports/policy_corpus.py`), which REFUSES when unconfigured rather than falling back to an ungoverned search |
| Runtime guardrail: prompt-injection and jailbreak defence, output screening | **Hrz1** `agent-guardrail-gateway` | a mandated dependency this repo has NOT yet bound (the R1 row in `COMPLIANCE.md` says so). In-repo redaction is in place; screening belongs behind a `GuardrailPort` |
| Agent registry, versioning, identity, entitlements | **Hrz3** `agent-registry` | publishes its A2A card at `/.well-known/agent-card.json`, built from the same tool table the runtime binds |
| AI-quality / eval / model-risk promotion gate | **Hrz4** `model-quality-gate` | owns promotion under the bundle id `claims-integrity-investigator`; the offline gate mirrors its thresholds |
| Observability, tracing, immutable WORM audit, FinOps | **Hrz5** `agent-observability` | writes audit events and exports structural-only spans to it; the in-repo hash chain is the offline stand-in |
| Human review / maker-checker console | **Hrz7** `human-review-console` | routes every assessment's escalation to it (R8); it does not re-implement the console or its approval workflow |
| Organised-fraud ring detection and the signals behind it | **G1 to G5**, the financial-crime suite (`aml-alert-triage`, `sanctions-screening`, `app-fraud-interdiction`, `account-takeover-investigator`, `soc-fraud-fusion`) | consumes a linkage signal as a DATA FEED through `ports/fraud_linkage.py` and scores it; it does not detect rings |
| Project-intake architecture and requirements validation | **Rsk3** `architecture-validator` | an intake action for the adopting project (rule R6), not a runtime call |

So the guardrail, the knowledge base, the registry, the eval platform, the audit sink, the
review console and the fraud-ring detection are *dependencies*, not features of this repo.

### Where exactly does Ins1's responsibility end?

At the recommendation, handed to a named human. Ins1 does not pay or deny a claim, post or
release a reserve, notify or correspond with a claimant, open or work an SIU case file, refer a
matter to a regulator or law enforcement, or price or renew a policy. It also does not decide
who may see a claim: object-level authorisation over a queryable claim store is an open item
(the Tenant isolation row in `COMPLIANCE.md`), and the tenant partition it does carry is
asserted on the outbound review. Downstream systems act on an approved disposition; Ins1 hands
them a cited, replayable one.

### How does this relate to the other financial-crime systems in the catalog?

Ins1 sits in the FCC category because the disposition is a per-claim fraud-indicator decision
about an external claimant, but it is the insurance-claims point of that family. **G1** triages
AML transaction-monitoring alerts, **G2** resolves sanctions and payment-message screening hits,
**G3** scores in-flight payments for scam and authorised-push-payment fraud, **G4** investigates
account takeover, and **G5** fuses security and fraud alerts for a SOC. Their organised-fraud
output is an input here, never a capability to duplicate. The nearest structural sibling outside
FCC is **Doc6**, the complaints and conduct file review, whose grounded-drafting skeleton this
repo's drafter mirrors.

### Can I use this for a different kind of file review?

Yes, that is the point of the layering. The kernel, the three profiles, the redact-before-model
ordering, the refuse-rather-than-guess rule, the citation convention, the eval gate and the R8
routing all transfer. What you replace is the schedule and clause semantics in
`coverage_engine.py`, the indicator rules in `red_flags.py`, the taxonomies in `models.py`, the
extraction grammar and the fixtures. See [`../ADOPTING.md`](../ADOPTING.md) and
[adoption-faq.md](adoption-faq.md).

### How do I see it working?

`make demo` runs the presenter-paced walkthrough over eight real steps against the offline
profile: bind the stack, a clean claim assessed and routed, an organised-fraud claim referred to
SIU under dual control, personal data masked before the model and the audit write, what the
reviewer actually receives, the audit trail verified and exported, a rewritten record detected,
and the exit profile failing fast. `make demo-selftest` runs the same arc headless and asserts
every narrated claim, so a step the demo makes but nobody verifies cannot exist.
`make demo-static` renders the panels as dependency-free HTML for screenshots. Everything runs
on synthetic, obviously fictional claims with no cloud and no API key.
