# Compliance FAQ

For compliance, model-risk and privacy teams assessing Ins1's regulatory posture.
Cross-references: [`../../COMPLIANCE.md`](../../COMPLIANCE.md) (the full principle and rule map
with an Evidence column, plus the adopter-owned crosswalk), [`../../SPEC.md`](../../SPEC.md),
[`../model-card.md`](../model-card.md).

### Is this deciding claims autonomously?

No. It is a **decision-support** service. Every assessment, including a clean accept, sets
`requires_human_review=True` and carries `Decision.ESCALATED`, and the escalation is ROUTED to
the **Hrz7** Human-Review and Maker-Checker Console in the same call that produced it (rule R8),
never terminated in a local boolean. The API, the CLI and the agent tool all route before
returning, and the response carries a `review_ref` so a caller can distinguish a routed
escalation from one that stopped locally. An SIU-refer maps to CRITICAL, which the outbound
payload marks for dual control (two approvals). The managed router REFUSES when no console is
configured rather than swallowing the escalation, and the on-premises placeholder raises rather
than dropping it. **Nothing is paid, denied or reserved by this service.**

### Is the consequential decision explainable and replayable?

Yes, because a model does not make it. The per-line coverage verdicts and the indemnity quantum
come from `domain/coverage_engine.py`, the fraud indicators and score from
`domain/red_flags.py`, and the disposition from `recommend()` in
`domain/assessment_service.py`, all pure stdlib. Money is integer cents end to end, so no figure
picks up a float rounding error. Each indicator carries a stable fingerprint
(`red_flags.signal_key`, a SHA-256 over the normalised identifying evidence), so two runs over
the same file produce the same keys and two runs diff exactly. Every figure carries a `Citation`
back to the invoice line, claim document or policy clause behind it. An adjuster or an auditor
can recompute the whole assessment from the same inputs without the model, and
`tests/unit/test_assessment_service.py::test_the_numbers_are_identical_whatever_the_generator_returns`
proves a model change cannot move one.

### How is claimant personal data handled?

This service genuinely processes personal data, so it redacts rather than declaring the control
not applicable. Masking uses the shared `pii-kit` rows selected by `domain/pii.py`
(`JURISDICTIONS` is SG, HK, JP, AU by default, national-id rows first and universal email and
phone rows last) and happens at four boundaries: before the extraction model sees the claim file
(`assessment_service._redact_raw`), before the audit write (`_record`), before the review
payload leaves the process (`adapters/_review_payload.py`, against EVERY jurisdiction's rows
because the console is a shared sink), and over every string of an agent tool result
(`agent/tools.py:_redacted`, because a tool result becomes model context). Trace spans carry
STRUCTURAL attributes only, deliberately: a trace backend has no redaction stage, a wider read
audience and no retention rule written against a regulator's requirement, so no claim id,
claimant, file text or narrative reaches one.

The runtime guardrail and DLP gateway itself is the sibling **Hrz1** system, and this repo has
NOT yet bound a `GuardrailPort` to it. The R1 row in `../../COMPLIANCE.md` states that plainly
rather than claiming coverage; treat prompt-injection screening as an open dependency, not a
shipped control.

### Is the audit trail good enough to rely on?

Within limits the repo states rather than glosses. Every assessment writes an already-redacted
`AuditEvent` with the action, the verified actor, the decision, the severity band and the
citation set. The local store is append-only and hash-chained, with `UPDATE` and `DELETE`
triggers, and is externally ANCHORED: the chain alone cannot detect a truncated tail, because
dropping the newest rows leaves a shorter chain that still verifies, so `audit_anchor_path`
writes the chain head to a file on a different volume and once store and anchor disagree the
service refuses to append rather than re-anchoring. `tests/unit/test_audit_anchor.py` proves
both halves including the control case. That is the offline stand-in. Production retention is
the locked Cloud Logging WORM bucket (`infra/terraform/logging_worm.tf`, 180-day floor,
irreversible lock) and the enterprise sink is **Hrz5**. The retention schedule and the legal
basis for the trail are adopter-owned.

### What is the model-risk story?

Modest and honestly bounded. `eval/run_eval.py --mode smoke` runs in the offline gate on every
change, driving the real `ClaimAssessmentService` over a golden set and scoring six metrics
against the DATASET'S OWN hand-written oracle rather than the pipeline's verdict:
`decision_accuracy` (0.80), `quantum_accuracy` (0.99), `red_flag_accuracy` (0.80),
`review_safety` (1.00), `groundedness` (0.99) and `pii_safety` (0.99). Every metric is proved
able to go RED before it is trusted (`assert_each_can_go_red`): a metric that cannot distinguish
a wrong answer from a right one is not a metric, and `pii_safety` additionally uses a
pack-independent planted-literal oracle so it fires even if a pattern row is broken.

`--mode gate` is the promotion authority and delegates the verdict to the sibling **Hrz4**
AI-quality and model-risk platform under the bundle id `claims-integrity-investigator`,
refusing to run off the managed profile. Two caveats a model-risk reviewer should record:
registering that bundle with Hrz4 is still open (the P-08 and R5 rows), and the offline eval
scores the deterministic offline generator, not a live model, so it is evidence about the
engines rather than about a hosted model. See [`../model-card.md`](../model-card.md).

### Is data residency enforced, or only documented?

Enforced at deploy time. The region is chosen once in `infra/terraform/render.tf.json`
(`asia-southeast1`) and read by both the application settings and Terraform.
`infra/terraform/variables.tf` validates the effective region against the `allowed_regions`
residency allowlist at plan time, the allowlist defaulting to exactly the rendered region;
`org_policy.tf` pins `constraints/gcp.resourceLocations` to that region's location group and
forbids exportable service-account keys; and the CMEK key ring, the locked WORM bucket and, when
the opt-in serving edge is enabled, the Cloud Run service and its regional network endpoint
group are all created in it. `infra/terraform/production_edge.tftest.hcl` is the executable
check, running `residency_defaults_are_in_country` and
`reject_region_outside_the_residency_allowlist` against a mocked provider with no project and no
credentials. The remaining gap is build wiring, not enforcement: this repo has no `tf-check`
make target and no `terraform` CI job, so those runs happen only when somebody types
`terraform -chdir=infra/terraform test`. The P-03 row in `../../COMPLIANCE.md` records exactly
that.

### Which regulators does this map to?

`../../COMPLIANCE.md` maps the catalog's own P-01 to P-13 principles and R1 to R8 dependency
rules to concrete code with an Evidence column naming real files, aligned to MAS TRM, APRA CPS
234 and CPS 230, HKMA and PDPA-class regimes. The mapping from those rows to a specific
regulation, and the judgement that a control is SUFFICIENT for it, is deliberately
**adopter-owned**: it depends on your risk appetite, your regulator, your licence conditions and
your existing control library. No row should be quoted as regulatory assurance. What an adopter
is expected to add in their own library is listed at the foot of that file: the crosswalk to
their control ids, the risk acceptance for every row still Partial or TODO at go-live, a
second-line review of the deterministic policy in `domain/` (it is bank-owned logic, not a
vendor default to inherit unexamined), and the retention schedule for the audit trail. For
insurance specifically, note that conduct obligations around claims handling and repudiation
notices are not modelled here at all.

### Who owns the numbers that drive a repudiation?

You do, and the repo is built so you cannot own them by accident. The fraud-score bands, the
per-indicator uplifts, the late-notification window, the velocity pair, the round-amount pair
and the staged-loss marker phrases all live as data in the `policy:` block of
`config/settings.yaml`, frozen into `domain/policy.py:AssessmentPolicy` with an `as_of` stamp
that every assessment records, so an assessment can always be traced to the policy version that
produced it. The shipped values are fictional defaults, not a recommendation. Section 4 of
[`../ADOPTING.md`](../ADOPTING.md) lists each one; sign them off with your claims and SIU
functions and pin them in a test.

### Can we run it against real claims today?

Not without your own legal, security and model-risk sign-off, and there is a technical guard as
well as a policy one. Every fixture claimant is obviously fictional, every identifier synthetic
and every domain `.example`. The managed profile is refused at process start while any adapter
in `managed_readiness.py:INCOMPLETE_MANAGED_OPERATIONS` is bound, so a `gcp` deployment cannot
quietly become healthy on placeholder adapters. The adoption checklist in
[`../ADOPTING.md`](../ADOPTING.md) section 6 lists what must precede live use: your residency
region, your IdP, your policy numbers, your jurisdictions, your fixtures and golden set, and the
managed adapters implemented and integration-tested.
