# Security FAQ

For an AppSec reviewer sizing up this repo (Ins1, the Claims Integrity Investigator). It
explains what the attack surface is, what is deliberately out of scope and why that is honest
rather than a gap, and where the evidence lives.

## What does this system actually process?

Insurance claim files: FNOL text, adjuster notes, invoice lines, the policy schedule and a
claimant's prior-claims record, fetched through `ports/claim_file.py` and
`ports/claims_history.py`. Unlike most catalog systems, this one **does** handle personal data
about an external individual, so the redaction rule is load-bearing here rather than a
formality. It produces a per-line coverage verdict, an indemnity quantum in integer cents, a set
of fingerprinted fraud indicators with a score, and an accept / investigate / decline /
SIU-refer recommendation. It pays nothing, notifies nobody and opens no case file: it hands a
cited recommendation to a human.

## Where does redaction happen, and can I prove it?

At three boundaries, not one, all using the shared `pii-kit` rows selected by
`domain/pii.py:PII_PATTERNS`:

1. **Before the extraction model.** `domain/assessment_service.py:_redact_raw` masks every
   document in the claim file before `self._extraction.extract(...)` is called, so a managed
   multimodal extractor never sees a raw identifier. `tests/unit/test_assessment_service.py::test_redaction_happens_before_the_extraction_model_sees_the_file`
   wraps the real extractor in a spy adapter, drives a fixture claim carrying a planted
   synthetic NRIC, and fails if that literal reaches the port.
2. **Before the audit write.** `ClaimAssessmentService._record` redacts the summary and
   narrative before the `AuditEvent` is constructed, so nothing raw reaches the WORM store.
3. **Before the review payload leaves the process.** `adapters/_review_payload.py` scrubs the
   subject, summary and every citation snippet against EVERY jurisdiction's rows plus the
   universal email and phone rows, not just this deployment's selection, because the Hrz7
   console is a shared sink. `tests/unit/test_review_routing.py::test_the_payload_is_redacted_before_it_leaves_the_process`
   is the standing gate.

A fourth path exists for the agent surface: `agent/tools.py:_redacted` walks a whole tool result
and masks every string in it, because a tool result becomes model context (P-04) while an API
response to the caller who supplied the text is not the same thing.

## How is identity handled? Can a caller spoof the actor?

No. `api/schemas.py:AssessRequest` carries only `claim_id`; there is no `actor` field to spoof.
`api/app.py:get_principal` resolves a `Principal` server side through the bound `IdentityPort`
and that principal is the audit actor and the review maker. Under `gcp`,
`adapters/gcp/identity.py:IapIdentityAdapter` verifies the IAP-injected assertion against the
configured `CLAIMSINTEG_IAP_AUDIENCE` and IAP's own key set, and checks the issuer itself; an
unset or emptied audience REFUSES rather than verifying against no audience. Under `local` the
personas are seeded dev identities picked with `X-Dev-Persona`, and the adapter refuses to
construct unless `local` was chosen deliberately. Under `onprem` nobody is resolved at all.

`get_principal` deliberately does not use the commons' collapse-everything-to-401 helper: a
caller who could have authenticated and did not gets 401, while a deployment that can
authenticate NOBODY raises `EndUserAuthUnavailableError` carrying its own status and a reason,
so an operator is not sent hunting for a missing credential that would not have helped.

## What stops an unauthenticated peer reaching the routes?

The loopback exposure guard, registered at MODULE scope in `api/app.py` because the Dockerfile
`CMD` and `make run-api` serve the app object, so a guard bound only in `main()` would never run
in a shipped process. `tests/unit/test_serving_path_exposure.py` is the standing gate.

The guard's posture is derived from the identity BINDING and from nothing else: an adapter
declares `VERIFIED`, `CLIENT_ASSERTED` or `UNIMPLEMENTED` (`ports/identity.py`), and silence
reads as client-asserted. `CLAIMSINTEG_S2S_TOKEN` takes no part in that decision, which is the
point: it authenticates a calling SERVICE and no end user, and while it did feed the guard,
setting it switched the guard OFF for the end-user routes it was protecting.
`tests/unit/test_end_user_auth_posture.py` walks the guard's argument through the constants it
names and fails the build if a credential reappears at any depth. Interactive docs (`/docs`,
`/redoc`, `/openapi.json`) are ABSENT rather than guarded under any profile except the
deliberate offline `local`, because a guard the profile has stood down is no guard.

## Are there secrets in the repo?

No literal secret material. `config/settings.yaml` carries only `${VAR:-default}` interpolation
tokens; `.env.example` documents non-secret variable names; `.env.secrets.example` documents the
secret NAMES with placeholder values. Inbound and outbound credentials are deliberately distinct
variables: this service's own inbound `CLAIMSINTEG_S2S_TOKEN` against the outbound
`HRZ7_S2S_TOKEN` / `HRZ7_S2S_SIGNING_KEY` the review client uses. Every security-relevant
environment read resolves three states, and `tests/unit/test_three_state_env_reads.py` walks the
AST of `src/`, `scripts/` and `eval/` and fails the build on any two-state read that ships.

## What is the supply-chain posture?

Committed lockfiles (`requirements-dev.lock`, `requirements-gcp.lock`, python 3.12) installed
with `--no-deps` by `make install`, CI and the Dockerfile, with the four commons packages
(`pii-kit`, `hex-service-kit`, `agent-eval-kit`, `review-kit`) declared by tag in
`pyproject.toml` and pinned in the lockfiles to the 40-character COMMIT each tag resolved to,
because a tag can be moved and a commit cannot. `ruff` is pinned exactly. The image is
multi-stage, digest-pinned and non-root; Actions are SHA-pinned; `pip-audit` is a hard CI
failure via `make audit`. `tests/unit/test_repo_artifacts.py` asserts the three-way agreement
offline.

## Is the audit trail tamper-evident?

Yes, within honest limits, and the limit is named rather than glossed.
`adapters/local/audit.py` wraps `hex_service_kit.audit.HashChainedAuditLog`. The hash chain
catches an in-place edit, an interior deletion and a reorder, but it CANNOT catch a truncated
tail on its own, because dropping the newest rows leaves a shorter chain that verifies
perfectly. That gap is closed by an external head anchor (`audit_anchor_path`, configured to a
file on a different volume), and `tests/unit/test_audit_anchor.py` proves both halves including
the control case where the same truncation goes undetected without an anchor. Once store and
anchor disagree the service refuses to append rather than re-anchoring. This is still the
offline stand-in: production tamper-evidence is the locked Cloud Logging WORM bucket
(`infra/terraform/logging_worm.tf`) and the enterprise sink is Hrz5.

## What about the browser surface?

`ui/` is an embeddable Next.js micro-frontend whose whole security boundary is one policy module
(`ui/lib/embed-policy.mjs`) and one server-side identity module (`ui/lib/server/identity.ts`).
Every client-supplied actor, tenant, role, ACL and authorization header is discarded before a
request is forwarded; the service credential is read from the server environment and never
reaches a bundle; framing and CORS are per-tenant allowlists that refuse a wildcard however it
is written, and refuse from `next.config.mjs` so the refusal is a boot refusal.
`ui/tests/three-state-env-reads.test.mjs` scans every shipped `.mjs`, `.ts` and `.tsx` with the
same three-state rule the Python side uses, and `tests/unit/test_ui_surface.py` holds the UI,
its dependabot ecosystem and its CI job consistent in both directions.

## What is explicitly out of scope for this repo?

Prompt-injection screening and output filtering: those belong to the **Hrz1** guardrail gateway,
and this repo has not yet bound a `GuardrailPort` to it (the R1 row in `../../COMPLIANCE.md`
says so plainly rather than claiming coverage). Governed retrieval and its ACL model are
**Hrz2**'s. Agent identity and entitlements are **Hrz3**'s. Model-risk promotion is **Hrz4**'s.
The enterprise WORM sink and tracing backend are **Hrz5**'s. The review console, including its
own re-redaction and its approval workflow, is **Hrz7**'s. Organised-fraud ring detection is the
**G1 to G5** financial-crime suite's; this repo consumes a linkage signal as a data feed and
scores it. Ins1 does not re-implement any of them, and a fork should not either.
