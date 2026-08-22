# Portability FAQ

For architecture, cloud, and exit-planning reviewers who want to know how real the "no lock-in"
claim is for Ins1, and how an off-cloud or sovereign exit would actually work.

## What is the no-lock-in claim, concretely?

`domain/` and `ports/` are the code a client owns outright after an extraction: the coverage
rules, the fraud-indicator rules, the policy numbers and the port contracts. Neither may import
a cloud SDK, a web framework or an HTTP client. `tests/unit/test_core_purity.py` enforces that
as an **allowlist** rather than an SDK blocklist (a blocklist rots the day a vendor renames a
distribution): the only non-stdlib imports permitted in the core are this package itself and the
named workspace kits, which are themselves stdlib-pure. `EXEMPT_IMPORTS` in that module is
currently empty, so there is no debt hiding behind a written exemption. A lazy import inside a
function body on a path profile construction never exercises is caught too, because the scan is
static AST rather than runtime.

## What are the profiles?

`CLAIMSINTEG_PROFILE` selects the whole adapter stack, and it has three values plus a fourth
state:

- **`local`** is a real, working, SDK-free offline stack: fixture claim files and policy
  corpus, a deterministic extractor over the fixtures' marker grammar, a deterministic grounded
  narrator, a hash-chained SQLite WORM audit log, seeded dev personas, and a review outbox that
  actually enqueues. This is the dev, test, CI and demo default, and the working proof the
  domain runs entirely off-cloud.
- **`gcp`** is the managed stack (Cloud Logging WORM, IAP identity, Cloud Trace or OTLP to the
  Hrz5 collector, the Hrz2 governed-RAG retrieval, the Hrz7 review intake, the Hrz4 promotion
  client), with every SDK import lazy so the other profiles import with nothing installed.
- **`onprem`** is fail-fast placeholders that satisfy the same Protocols and raise
  `NotImplementedError`, naming the migration target. They prove the ports are honest exit seams
  rather than decoration.
- **Unset** is a fourth state and NOT a silent `local`: the offline adapters still bind, but the
  seeded personas are refused, no S2S scheme is selected, every relaxation sees `unconfigured`
  and the exposure guard refuses every route to a non-loopback peer. Set-and-empty and
  set-and-unknown both raise at import, before the process can serve anything.

## Is the portability claim tested, or just asserted?

Tested, and bounded. `make portability` runs `scripts/portability_demo.py`, which exits non-zero
on any failed check and prints a pass or fail per named claim: `port map complete`,
`adapters construct and conform`, `offline family answers`, `exit family refuses`,
`rewrite detected`, `truncation detected when anchored`, `record leaves intact`, and
`no cloud SDK imported`. Note the third: the offline family must ANSWER a canonical call, not
merely fail to raise.

Alongside it, `tests/contract/test_port_parity.py` asserts set equality across the five places a
port must be registered (`ports/__init__.py:PORT_PROTOCOLS`, `config.DEFAULT_BINDINGS`, the
`Container` accessor, the `adapters:` block of `config/settings.yaml`, and a `PortCase` in
`tests/contract/canonical.py`), in both directions, so a port bound but unregistered fails the
build instead of running with no enforcement. `tests/contract/test_behavioral_parity.py` drives
the same canonical request through each family's boundary.

## What does the portability demo deliberately NOT prove?

It says so itself, in its own module docstring, because an unbounded claim is the one an auditor
disproves for you: it does not prove that an on-premises deployment exists or that anyone has
run one, it proves nothing about infrastructure, model, network or whole-system portability, and
it says nothing about the managed profile's live behaviour, which needs a cloud project and
lives in `tests/integration/` (marked, and deselected by the offline gate).

## How would a sovereign or on-prem exit actually go?

The `onprem` profile is the scaffold and [`../onprem-migration.md`](../onprem-migration.md) is
the step-by-step. Each placeholder marks a seam where the client supplies their own component:
their claim-document store, their claims-history warehouse, their extraction and model hosts,
their policy-wording corpus, their IdP, their audit store, their review queue. Because the
domain never changes, the exit is an adapter exercise rather than a rewrite.

Two seams have consequences worth knowing before you plan one. The identity placeholder refuses
with a STATUS and a REASON rather than a bare crash, and a replacement adapter must set
`end_user_auth = VERIFIED` on its class or the exposure guard reads it as client-asserted and
keeps the service on loopback: that is the fail-closed default, not a bug. And the review-router
placeholder RAISES rather than returning quietly, because rule R8 does not relax on exit; an
adapter that dropped the escalation would leave the service auto-executing with the appearance
of review.

## How is data residency handled?

The region is chosen once, in `infra/terraform/render.tf.json` (`asia-southeast1`), and both the
application settings (`region:` in `config/settings.yaml`) and the Terraform stack read it. It
is enforced at deploy time rather than described: `infra/terraform/variables.tf` validates the
effective region against the `allowed_regions` residency allowlist at plan time (the allowlist
defaulting to exactly the rendered region), `org_policy.tf` pins
`constraints/gcp.resourceLocations` to that region's location group, and every regional resource
is created in it, the CMEK key ring, the locked WORM bucket, and the Cloud Run service with its
regional network endpoint group when the opt-in serving edge is enabled.
`infra/terraform/production_edge.tftest.hcl` is the executable check and runs against a mocked
provider with no project and no credentials. Its one gap is build wiring: this repo has no
`tf-check` make target and no `terraform` CI job, so those runs only happen when somebody types
`terraform -chdir=infra/terraform test`. Moving to another region is a tfvars change to the
`region` / `allowed_regions` pair, not a fork.

## Can the data be exported in an open format?

Yes. The audit trail exports to JSON Lines and reloads into a foreign store with its hash chain
intact, which is the `record leaves intact` check in the portability tour. Assessment artifacts
are frozen dataclasses serialised through `hex_service_kit.serialization.to_jsonable`, and money
is carried as integer cents throughout (`domain/models.py:money` only formats for display), so a
figure cannot pick up a float rounding error on the way out.

## What is honestly NOT portable today?

The managed profile is not finished, and the repo refuses to pretend otherwise:
`managed_readiness.py:INCOMPLETE_MANAGED_OPERATIONS` names the adapters that are still
construction-only placeholders, and the API preflight refuses to start a `gcp` process while any
of them is bound. Production tamper-evidence remains the locked WORM bucket's and Hrz5's job,
not the local hash chain's. And the sibling platform services (Hrz2 retrieval, Hrz4 promotion,
Hrz5 audit and tracing, Hrz7 review) are dependencies you re-point at your own equivalents on
exit, not code this repo can hand you.
