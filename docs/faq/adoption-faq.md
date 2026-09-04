# Adoption FAQ

For an engineering lead forking `claims-integrity-investigator` as their insurer's claims-review base. The step-by-step is
[`../ADOPTING.md`](../ADOPTING.md); this answers the "will it hurt later?" questions.

### How do I rebrand it for my organisation?

`scripts/rename_fork.py` rewrites the python package name `claims_integrity_investigator` (which
is also the console-script name), the `CLAIMSINTEG` environment prefix, the distribution and
resource id `claims-integrity-investigator`, and optionally the Terraform `name_prefix`
default, in one pass. It previews by default and writes nothing without `--yes`. Then recreate
the venv, `pip install -e ".[dev]"`, and run `make gate`.

There is deliberately **no `--cli` flag and no `--dist` flag**. The `[project.scripts]` entry
point is named after the package, so `--package` renames the CLI too; and `--resource` is one
literal doing four jobs (the distribution name, the GitHub id in `[project.urls]`, the A2A
agent-card `provider`, and the `model-quality-gate` eval bundle id), which are the same string on purpose so a
fork's promotion record and its discovery card cannot disagree about which system they describe.
A second flag for either could only drift out of step.

`--name-prefix` is handled differently from the whole-tree replacements, for a reason worth
knowing if you extend the script: it is a short word, and a whole-tree replacement of a short
word is how a rename script corrupts prose. It is rewritten only inside its own `variable
"name_prefix"` block in `infra/terraform/variables.tf`, and its current value is read from that
file rather than hardcoded, so a second rename still works.

### If several insurers fork this, how does each take upstream fixes?

Track upstream via **git tags**. The repo declares a core-vs-adopter-owned boundary
([`../ADOPTING.md`](../ADOPTING.md) section 2): upstream owns `domain/kernel.py`, `ports/`,
`tests/contract/`, the eval harness mechanics, the `config.py` hexagon wiring, the fail-closed
API scaffolding and CI; you own the `policy:` values, the two engines and the artifact models,
`adapters/onprem/*`, the fixtures, the golden set, UI theming and the regulator crosswalk.
Rebase your adopter-owned changes onto each release rather than merging `main` continuously, so
conflicts stay in the files you were told to expect them in.

### Is there a real kernel module I can keep untouched?

Yes, unlike some catalog repos. `domain/kernel.py` holds the vertical-neutral machinery
(`Citation`, `AuditEvent`, `Severity`, `Decision`, `utcnow`) and knows nothing about insurance;
`domain/models.py` holds this vertical's artifacts and imports the three neutral types from the
kernel rather than redeclaring them. `tests/unit/test_core_purity.py` keeps the whole core
(`domain/` and `ports/`) importing nothing but the standard library, this package and the named
workspace kits, and its `EXEMPT_IMPORTS` map is currently empty, so there is no written debt.

### How do I add a new outbound dependency (a new port)?

There is a fixed ten-row touch list in [`../../CONTRIBUTING.md`](../../CONTRIBUTING.md), and the
first six rows are enforced rather than advisory. A port lives in FIVE places at once
(`ports/__init__.py:PORT_PROTOCOLS`, `config.DEFAULT_BINDINGS`, a `Container` accessor, the
`adapters:` block of `config/settings.yaml`, and a `PortCase` in `tests/contract/canonical.py`),
four of which can be satisfied while the fifth is missing, which yields a port with zero
enforcement and a green build. `tests/contract/test_port_parity.py::test_every_home_of_the_port_set_agrees_exactly`
asserts set equality across all five in both directions. Then bind it in all three families:
`local` must WORK offline, `gcp` imports its SDK lazily inside the method, and `onprem` must
RAISE. A placeholder that returns successfully is a false portability claim, and one that raises
a bare `NotImplementedError` on a serving path answers 500 with no body, so raise a subclass
carrying a status and a reason (see `adapters/onprem/identity.py` for the pattern).

### How do I add a new deterministic engine or rule?

A sub-service is pure domain: a module under `domain/` that is stdlib only and deterministic,
constructed in `ClaimAssessmentService.__init__` and threaded through
`build_assessment_service`, with unit tests that pin its behaviour. Two rules are not
negotiable: the consequential decision stays pure and replayable (a model may narrate it, never
produce it), and every consequential result escalates through `ReviewRouterPort` rather than
terminating in a boolean. If your rule needs a new number, put the number in the `policy:` block
of `config/settings.yaml` and read it off `AssessmentPolicy`, not as a module constant in the
engine: the whole point of `domain/policy.py` is that no weight hides in an engine.

### Can I retune the scoring numbers without touching code?

Yes, fully, and this repo is unusual in the catalog for it. Every consequential number is
already data: the `policy:` block of `config/settings.yaml` is loaded into the frozen
`domain/policy.py:AssessmentPolicy` and injected into `RedFlagEngine` and `recommend()`. An
absent block takes the shipped fictional defaults; a present block overrides only the keys it
names; and `as_of` stamps every assessment with the policy version that produced it. Retuning
the SIU-refer band, the per-indicator uplifts, the late-notification window, the velocity pair,
the round-amount pair or the staged-loss marker phrases is a settings edit plus a test that pins
your values. What is NOT in that block is the eval thresholds, which live in the `THRESHOLDS`
map in `eval/run_eval.py`, and the coverage arithmetic (cap then excess), which is structural
rather than a tunable.

### How do I change the taxonomies?

`Recommendation`, `CoverStatus`, `RedFlagKind` and `DocumentKind` in `domain/models.py` are
`LenientStrEnum` members from the commons, so a member IS its wire value and serialized JSON
carries the enum string. Adding a red-flag kind means adding the member, the rule method on
`RedFlagEngine`, an `uplifts` entry in settings, and a unit test; `AssessmentPolicy.uplift_for`
returns 0.0 for a kind the adopter removed, so a partial map fails soft rather than crashing.
Note that `recommend()` special-cases `organised_fraud_link` by value: an organised-fraud match
refers to SIU regardless of score, so check that rule if you rename or replace that kind.

### Will the demo rot after I diverge?

It is guarded, and the guard has its own required check rather than living in `make gate` (the
gate proves the service and must stay fast and offline). A demo step exists in exactly two
places, `demo.STEPS` and `walkthrough.CHECKS`, and `tests/unit/test_demo_surface.py` holds the
two sets equal, so a claim the demo makes but nobody verifies cannot exist. `make demo-selftest`
runs the whole eight-step arc headless, driving the REAL demo server over loopback HTTP and
asserting that the service reached the state each narration claimed. No browser engine is
installed or needed. If you rewrite the arc, keep the pairing.

### Does CI run for my fork out of the box?

Yes, and it needs no cloud credentials and no org secrets. the hosted GitHub Actions check is a thin
caller of the shared reusable hard-gate workflow pinned to a TAG (not a branch, so the meaning
of the gate cannot change under you), running the offline gate on python 3.12 and 3.13 plus the
eval. One extra job is worth knowing about: `iap-matrix-path` names
`tests/unit/test_iap_crypto_matrix.py`, which installs the RUNTIME lockfile so the one adapter
whose declaration stands the exposure guard down is not the one adapter nobody tests. It is
still offline, minting its signing key in process. Note the eval measures the reference fixtures
and golden cases until you rebuild them for your own book: that is an explicit adoption step,
not a silent pass.

### What is definitely still open when I fork?

The managed profile. `managed_readiness.py:INCOMPLETE_MANAGED_OPERATIONS` names the adapters
that are construction-only placeholders (`claim_file.fetch`, `claims_history.history`,
`extraction.extract`, `fraud_linkage.linkage`, `generation.generate`,
`policy_corpus.retrieve`), and the API preflight
refuses to start a `gcp` process while any of them is bound rather than letting "production
ready" become a label. Beyond that, `../../COMPLIANCE.md` marks the `agent-guardrail-gateway` binding
(R1), the `agent-observability` binding (R2), the `agent-registry` registration (R4), the `model-quality-gate` bundle
registration (R5), resilience and kill switches (P-10), cost and latency control (P-11) and
object-level tenant isolation as open. Read those rows before you plan a go-live date.
