# Adopting this repo as your base

This repository (Ins1, the Claims Integrity Investigator) is a **common base** that an insurer,
a bancassurer or a TPA forks to build its own claims coverage and fraud-indicator review
service: it reads a claim file (FNOL, adjuster notes, invoices, the policy schedule), runs a
deterministic coverage and indemnity engine and a deterministic red-flag engine over it, drafts
a cited narrative that restates those figures, and routes an accept / investigate / decline /
SIU-refer recommendation to a human for sign-off. Forking it gives you a reusable hexagonal core
(a pure-stdlib domain, eleven typed ports, three swappable adapter profiles, a green offline
gate that needs no cloud and no credentials) plus a fully worked general-insurance vertical you
can keep, retune, or replace with your own lines of business.

This guide is the step-by-step for making it yours. It has two halves: a **mechanical rebrand**
(one script) and the **human decisions** the script cannot make for you.

> Related reading: [`ARCHITECTURE.md`](../ARCHITECTURE.md) (the port table and the request
> pipeline), [`SPEC.md`](../SPEC.md) (the locked contracts),
> [`CONTRIBUTING.md`](../CONTRIBUTING.md) (the file-by-file touch list for a new port or
> adapter), [`COMPLIANCE.md`](../COMPLIANCE.md) (principle to control map),
> [`model-card.md`](model-card.md) (the model boundary as built), the [`faq/`](faq/) directory.

---

## 1. What you keep vs what you rewrite

The domain is layered so the boundary is a physical module split, not a convention.
`domain/kernel.py` owns the vertical-neutral machinery and knows nothing about insurance;
`domain/models.py` holds this vertical's artifacts and imports `Citation`, `Decision` and
`Severity` from the kernel rather than redeclaring them.

| Layer | Where | For a new book of business |
|---|---|---|
| **Kernel** (vertical-neutral) | `domain/kernel.py` (`Citation`, `AuditEvent`, `Severity`, `Decision`, `utcnow`), every `Protocol` in `ports/` re-exported through `ports/__init__.py:PORT_PROTOCOLS`, and the `Container` wiring in `config.py` | keep untouched |
| **Policy** (your numbers) | the `policy:` block of [`config/settings.yaml`](../config/settings.yaml), frozen into `domain/policy.py:AssessmentPolicy`, plus the `THRESHOLDS` map in `eval/run_eval.py` | change by config, not by an engine edit |
| **Vertical** (the claims artifacts) | the artifact models in `domain/models.py` (`RawClaimFile`, `ExtractedClaim`, `CoverageAssessment`, `RedFlagAssessment`, `ClaimAssessment`, and the `Recommendation` / `CoverStatus` / `RedFlagKind` / `DocumentKind` taxonomies), the two engines `domain/coverage_engine.py` and `domain/red_flags.py`, the drafting prompt in `domain/drafting.py`, the jurisdiction selection in `domain/pii.py`, the offline fixtures in `adapters/local/_fixtures.py`, and the golden set in `eval/datasets/golden_cases.jsonl` | rewrite or reseed for your policies |

If your product is another **file-review with a deterministic verdict** (a complaint review, a
warranty or benefit adjudication, a trade-credit claim), most of the hexagon transfers directly:
the three profiles, the redact-before-model ordering, the refuse-rather-than-guess coverage
rule, the cited-figure convention, the eval gate and the Hrz7 review routing. What you replace
is the schedule and clause semantics in `coverage_engine.py`, the indicator rules in
`red_flags.py`, and the extraction grammar the offline adapter parses.

## 2. Core-vs-adopter-owned files (so upstream merges stay mechanical)

Upstream keeps evolving these; avoid diverging from them so you can pull fixes cleanly:

- **Upstream-owned** (take our changes): `domain/kernel.py`, every port under `ports/`,
  `tests/contract/` (including `canonical.py`, the one canonical call per port), the eval
  harness mechanics in `eval/run_eval.py`, the hexagon wiring in `config.py` (`Container`,
  `DEFAULT_BINDINGS`, `ProfileChoice`), the fail-closed API scaffolding in `api/app.py`, the
  managed-readiness preflight in `managed_readiness.py`, and the gate itself, which is the
  hosted GitHub Actions check rather than anything in this repository.
- **Adopter-owned** (yours; expect to edit): the `policy:` *values* in `config/settings.yaml`,
  the two engines and the artifact models, `domain/pii.py:JURISDICTIONS`, the whole of
  `adapters/onprem/*`, the offline fixture corpus in `adapters/local/_fixtures.py`, the golden
  set and thresholds, `ui/` theming and branding, the demo arc in `scripts/demo.py`, and the
  regulator crosswalk section of [`COMPLIANCE.md`](../COMPLIANCE.md).

Track upstream via git tags; rebase your adopter-owned changes onto each release rather than
merging `main` continuously, so conflicts stay inside the files you were told to expect them in.

## 3. The mechanical rebrand (one script)

`scripts/rename_fork.py` rewrites the python package name (which is also this repo's
console-script name), the `CLAIMSINTEG` environment prefix, the distribution and resource id
`claims-integrity-investigator`, and the Terraform `name_prefix` default, in one pass.
Preview first, then apply:

```bash
# Preview (writes nothing):
python scripts/rename_fork.py --package acme_claims_review \
    --env-prefix ACMECLAIMS --resource acme-claims-review \
    --name-prefix acme-claims --dry-run

# Apply:
python scripts/rename_fork.py --package acme_claims_review \
    --env-prefix ACMECLAIMS --resource acme-claims-review \
    --name-prefix acme-claims --yes

# Then recreate the environment (the distribution name changed) and prove it is green:
python3.12 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
make gate
```

There is deliberately **no `--cli` flag**: the `[project.scripts]` entry point in
`pyproject.toml` is named after the package, so `--package` renames the CLI too and a second
flag could only drift out of step with it. There is no `--dist` flag either, because
`--resource` is one literal doing four jobs at once: the distribution name in `pyproject.toml`,
the GitHub id in `[project.urls]`, the A2A agent-card `provider` in `agent/agent_card.py`, and
the Hrz4 eval bundle id (`_BUNDLE` in `eval/run_eval.py`). They are the same string on purpose,
so a fork's promotion record and its discovery card cannot disagree about which system they
describe.

`--name-prefix` is optional and is rewritten only inside its own variable block in
`infra/terraform/variables.tf` (default `ins1-svc`); the current value is read from that file
rather than hardcoded, so a second rename still works. Add `--include-docs` to sweep Markdown
prose too. The script deliberately does NOT touch the human decisions below.

## 4. The human decisions (the script can't make these)

1. **Region and residency.** The build is pinned to `asia-southeast1` (MAS / Singapore) in one
   place, `infra/terraform/render.tf.json`, which both the application settings
   (`region: ${GCP_REGION:-asia-southeast1}` in `config/settings.yaml`) and the Terraform stack
   read. To move it, set BOTH Terraform variables in your tfvars: `region` (the deploy region)
   and `allowed_regions` (the residency allowlist the region is validated against). The pair is
   checked at plan time by the cross-variable validation on `var.region` in
   `infra/terraform/variables.tf`, so an unapproved region fails at `terraform plan` rather than
   moving regulated data out of jurisdiction. This is enforcement, not documentation: the same
   region pins the CMEK key ring (`kms.tf`), the locked WORM audit bucket (`logging_worm.tf`),
   the `constraints/gcp.resourceLocations` Org Policy (`org_policy.tf`) and, when the opt-in
   serving edge is enabled, the Cloud Run service and its regional network endpoint group
   (`production_edge.tf`). What is NOT wired yet is the build hook: the executable proof lives in
   `infra/terraform/production_edge.tftest.hcl` (runs `residency_defaults_are_in_country` and
   `reject_region_outside_the_residency_allowlist`, against a mocked provider, needing no
   project and no credentials) and this repo has no `tf-check` make target and no `terraform` CI
   job, so it only runs when somebody types `terraform -chdir=infra/terraform test`. Wire that
   into your pipeline as part of adoption. See [`runbook.md`](runbook.md).
2. **Identity and the IdP.** This repo owns no login flow, and that is deliberate. The `gcp`
   profile verifies the Cloud IAP-injected assertion server side
   (`adapters/gcp/identity.py:IapIdentityAdapter`, which checks signature, issuer and the
   configured audience) and the audience comes from `CLAIMSINTEG_IAP_AUDIENCE`
   (`iap_audience` in `config/settings.yaml`), three-state: unset or emptied REFUSES every
   caller rather than verifying against no audience at all. The `local` profile serves seeded
   dev personas via `X-Dev-Persona` and refuses to construct unless `local` was chosen
   deliberately; `onprem` refuses outright and is where you implement your own IdP adapter. Wire
   your issuer ON the deployed service, not in this code, and set the audience.
3. **The assessment policy numbers.** These are your claims and SIU functions' numbers, not the
   code's, so they live as data in the `policy:` block of `config/settings.yaml` and are frozen
   into `domain/policy.py:AssessmentPolicy` with an `as_of` stamp that every assessment records.
   Own each of them deliberately: the fraud-score bands `siu_refer_score` (0.55) and
   `investigate_score` (0.30); the scoring shape `fraud_baseline` (0.05) and `max_uplift` (0.80);
   the per-indicator `uplifts` map (`late_notification` 0.10, `staged_loss` 0.25,
   `invoice_anomaly` 0.15, `claims_velocity` 0.20, `organised_fraud_link` 0.40);
   `late_notification_days` (30); the velocity pair `velocity_window_days` (365) and
   `velocity_threshold` (3); the round-amount pair `round_amount_floor_cents` (50000) and
   `round_amount_unit_cents` (100000); and the `staged_loss_markers` phrase list the adjuster-note
   scan looks for. An absent block takes the shipped fictional defaults, and a present block
   overrides only the keys it names. Add a test that pins your values: the shipped numbers are a
   reference, not your policy.
4. **The PII jurisdictions.** `domain/pii.py:JURISDICTIONS` is `("SG", "HK", "JP", "AU")` today
   and selects which `pii-kit` rows the redactor runs, in an order this vertical owns (national
   ids first, universal email and phone last). Set it to the markets you actually serve. Note
   that the outbound review payload is scrubbed against EVERY jurisdiction's rows regardless
   (`adapters/_review_payload.py`), because the Hrz7 console is a shared sink.
5. **Reference data is fictional.** Every claimant in `adapters/local/_fixtures.py` is plainly
   invented, every identifier is synthetic and every domain is `.example`; the fixture policy
   corpus is four made-up wordings and the fraud-linkage feed is a fixture. Replace all of it
   with your own synthetic data. **Do not run against real claim files without your own legal,
   security and model-risk sign-off.**
6. **Eval golden set and thresholds.** `eval/datasets/golden_cases.jsonl` holds four
   hand-labelled cases whose oracle (`expected_recommendation`, `expected_indemnity_cents`,
   `expected_flags`, and a `planted` synthetic identifier) was written by hand, never read back
   from the pipeline. Rebuild it for your policies, or your fork inherits a green gate that
   measures the WRONG book. The six metrics and their thresholds in `eval/run_eval.py`
   (`decision_accuracy` 0.80, `quantum_accuracy` 0.99, `red_flag_accuracy` 0.80,
   `review_safety` 1.00, `groundedness` 0.99, `pii_safety` 0.99) and the
   `assert_each_can_go_red` proof harness are generic; the golden cases are yours.
7. **Deployment posture.** The managed profile is deliberately NOT production ready out of the
   box: `managed_readiness.py:INCOMPLETE_MANAGED_OPERATIONS` names the adapters that are still
   construction-only placeholders, and the API preflight refuses to start a `gcp` process while
   any of them is bound. Implement and integration-test each one, empty the tuple, then flip the
   Terraform `managed_profile_implemented` local. Review the Dockerfile (digest-pinned base,
   non-root), `infra/terraform/` (Org Policy, CMEK, dry-run-first VPC-SC, locked WORM logging)
   and the loopback-by-default binding before you expose anything. See
   [`runbook.md`](runbook.md) and, for the exit path, [`onprem-migration.md`](onprem-migration.md).

## 5. Do not duplicate the platform

This repo is one system in a catalog of composable GRC systems. Several concerns it *touches*
are owned by sibling platform services; integrate rather than rebuild them. The full map is in
[`faq/features-faq.md`](faq/features-faq.md); the short version, and only integrations this repo
really has:

- **Hrz2** governed knowledge base: a HARD dependency. Policy wording is retrieved through the
  Governed-RAG service (`adapters/gcp/policy_corpus.py:Hrz2PolicyCorpusAdapter`, endpoint
  `CLAIMSINTEG_KNOWLEDGE_BASE_URL` / `knowledge_base_endpoint`), which REFUSES when unconfigured rather than falling
  back to an ungoverned search. Do not build a second retrieval path.
- **Hrz3** agent registry: this agent publishes its A2A card at
  `/.well-known/agent-card.json`, built from the same tool table the runtime binds
  (`agent/agent_card.py`). Register the card; take the agent's identity and entitlements from
  Hrz3 rather than minting them here.
- **Hrz4** AI-quality and model-risk gate: owns promotion. `eval/run_eval.py --mode gate`
  delegates the verdict to Hrz4 under the bundle id `claims-integrity-investigator` and
  refuses to run off the managed profile; the offline `--mode smoke` layer mirrors its
  thresholds. Register your bundle there, do not re-implement a promotion authority.
- **Hrz5** observability and immutable WORM audit: audit events and trace spans belong there
  (`adapters/gcp/audit.py`, `adapters/gcp/tracer.py`, which exports OTLP to the Hrz5 collector
  when `OTEL_EXPORTER_OTLP_ENDPOINT` is set). The in-repo hash-chained store is the offline
  stand-in, not the enterprise sink.
- **Hrz7** human-review and maker-checker console: every assessment escalates, and rule R8 says
  it is ROUTED, not flagged. `ports/review_router.py` has an adapter in every profile and the
  API, the CLI and the agent tool all route in the same call that produced the result. You wire
  your console endpoint (`HUMAN_REVIEW_URL`); you do not re-implement the console.
- **G1 to G5**, the financial-crime suite (AML alert triage, sanctions screening, scam and APP
  interdiction, account-takeover investigation, SOC fraud fusion): consumed as a DATA FEED
  through `ports/fraud_linkage.py`. The organised-fraud signal arrives as raw linkage and the
  scoring happens here; ring detection itself is theirs. The default binding is a local fixture,
  so name a live export when you have one.
- **Hrz1** guardrail gateway is a mandated dependency this repo has NOT yet integrated (see the
  R1 row in [`COMPLIANCE.md`](../COMPLIANCE.md)). Redaction is in place at every boundary, but
  prompt-injection screening and output filtering are Hrz1's job and belong behind a
  `GuardrailPort`, not in a second in-repo screening engine.

Ins1's responsibility ends at the recommendation. It does not pay a claim, post a reserve,
notify a claimant, open an SIU case file or file a regulatory report: those are downstream
systems acting on an approved disposition.

## 6. Adoption checklist

- [ ] Ran `scripts/rename_fork.py`, recreated the venv, `make gate` green.
- [ ] Set the Terraform `region` + `allowed_regions` pair to your in-country region, and wired `terraform -chdir=infra/terraform test` into your pipeline.
- [ ] Wired your IdP on the deployed service and set `CLAIMSINTEG_IAP_AUDIENCE` (this repo owns no login flow).
- [ ] Owned every `policy:` number with your claims and SIU functions, and pinned your values in a test.
- [ ] Set `domain/pii.py:JURISDICTIONS` to the markets you serve.
- [ ] Replaced the coverage and red-flag rules, the taxonomies and the extraction grammar for your policies.
- [ ] Replaced every synthetic fixture and the fixture policy corpus.
- [ ] Rebuilt the eval golden set and reviewed the six thresholds.
- [ ] Implemented and integration-tested the managed adapters, emptied `INCOMPLETE_MANAGED_OPERATIONS`.
- [ ] Reviewed the deploy posture (Dockerfile, Terraform, bind address, WORM retention lock).
- [ ] Wired your Hrz7 console and Hrz2 endpoint, and decided which sibling services you integrate vs stub.
- [ ] Recorded your baseline upstream tag so you can take future fixes.
