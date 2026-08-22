# Model card: Claims Integrity Investigator (Ins1)

This is a STARTER model card. It records the model boundary as built and the controls that must
be completed before a managed deployment. The deterministic engines are the system of record;
the model is a bounded, replaceable component on two ports and nothing else.

One fact up front, because it changes how the rest reads: **no live model is wired today.** Both
model-bearing adapters in the managed family (`adapters/gcp/extraction.py`,
`adapters/gcp/generation.py`) are construction-only placeholders that lazily import their SDK
and then raise `NotImplementedError`, and both are named in
`managed_readiness.py:INCOMPLETE_MANAGED_OPERATIONS`, so the API preflight refuses to start a
`gcp` process while either is bound. What ships and runs is the offline path: a deterministic
parser on the extraction port and a deterministic grounded narrator on the generation port. This
card describes the boundary that a real model will drop into, and what is already true of it.

## What the model does, and does not do

- **Does**: two jobs, both narrow. On the **extraction** port
  (`ports/extraction.py:ExtractionPort`) it turns an already-redacted claim file into structured
  evidence: claim lines with amounts and invoice references, the loss and notification dates, the
  policy schedule, and the adjuster-note prose. The managed intent is Document AI plus Gemini
  multimodal over documents and photos. On the **generation** port
  (`ports/generation.py:GenerationPort`) it drafts a three-to-four sentence narrative that
  RESTATES the figures and verdicts it is handed; its system instruction says exactly that, the
  recommendation is passed to it as "Recommendation (fixed)", and it is asked to cite each clause
  by source id. Both outputs are structured, schema-shaped and discarded on failure.
- **Does NOT**: produce any figure, status, score or verdict. The per-line coverage status and
  the indemnity quantum (sub-limit cap, then policy excess) are computed by
  `domain/coverage_engine.py:CoverageEngine`; the fraud indicators, their uplifts and the clamped
  fraud score by `domain/red_flags.py:RedFlagEngine`; the accept / investigate / decline /
  SIU-refer disposition by `recommend()` in `domain/assessment_service.py`; and the severity band
  by the `_SEVERITY_BY_RECOMMENDATION` map beside it. All of that is pure stdlib over integer
  cents, driven by the adopter-owned `AssessmentPolicy` in `domain/policy.py`, and none of it
  reads the model's output.
  `tests/unit/test_assessment_service.py::test_the_numbers_are_identical_whatever_the_generator_returns`
  drives the service with a substituted generator and asserts the figures do not move, so a model
  change cannot shift a cent. There is no speech, image-classification or scoring model anywhere
  in this repo.

## Boundary and validation

- **Redaction happens before the model, not only before the sink.** `_redact_raw` in
  `domain/assessment_service.py` masks every document in the claim file with the `pii-kit` rows
  from `domain/pii.py` BEFORE `self._extraction.extract(...)` is called. The ordering is the same
  on every profile, deliberately, so the guarantee does not depend on which adapter happens to be
  bound. The proof is a spy adapter:
  `tests/unit/test_assessment_service.py::test_redaction_happens_before_the_extraction_model_sees_the_file`
  wraps the real extractor, drives a fixture claim carrying a planted synthetic NRIC, and fails
  if that literal reaches the port. The audit write redacts again before the `AuditEvent` is
  built, and `adapters/_review_payload.py` redacts again before anything leaves the process.
- **What grounds the generation output, and what happens to a bad one.** The drafter renders the
  engines' coverage rows, the fraud indicators and the retrieved wording into the prompt, then
  parses the reply with `drafting._parse`: anything that is not a JSON object, or that carries no
  non-empty `narrative`, is DISCARDED and the deterministic template
  (`_deterministic_narrative`) is used instead. Any exception from the generation port is caught
  for the same reason: a disposition never waits on the model. Cited source ids are mapped back
  through `_citations_for` against the passages that were actually retrieved, so an id the model
  invented is dropped rather than rendered as provenance. Every narrative, drafted or fallback,
  is prefixed with a literal draft marker saying it is not a decision. Groundedness is measured,
  not assumed: the eval's `groundedness` metric (threshold 0.99) fails a case whose narrative
  does not contain the engine's own indemnity figure and fraud score.
- **The extraction output is not repaired either.** The offline extractor parses a strict marker
  grammar and returns whatever it found; a field it could not read stays empty, and the
  downstream engines treat an unreadable date as "rule does not fire" and a category missing from
  the schedule as `no_basis` with nothing payable. When no policy wording was retrieved at all,
  `CoverageEngine` marks every line `no_basis` and pays nothing rather than guessing cover from a
  schedule flag with no clause text behind it.
- **R8 human review, on every result.** Every assessment is consequential, so
  `requires_human_review` is always True and `Decision.ESCALATED` is always the decision, and the
  escalation is ROUTED to the Hrz7 console in the same call that produced it, by the API, the CLI
  and the agent tool alike. `tests/unit/test_review_routing.py` asserts the routing rather than
  the flag. Nothing auto-executes.

## Adapters and profiles

| Profile | Extraction adapter | Generation adapter | Behaviour |
|---|---|---|---|
| `local` | `adapters/local/extraction.py` | `adapters/local/generation.py` | No model at all. The extractor is a deterministic regex parser over the fixtures' `META` / `SCHED` / `LINE` marker grammar; the generator reads the figures the drafter already rendered into the request and restates them, returning `model="local-deterministic"`. Grounded by construction, SDK-free, byte-identical run to run. |
| `gcp` | `adapters/gcp/extraction.py` | `adapters/gcp/generation.py` | Intended Document AI plus Gemini multimodal, and Gemini on the Gemini Enterprise Agent Platform. Both currently lazily import the SDK and raise `NotImplementedError`; both are listed in `INCOMPLETE_MANAGED_OPERATIONS`, so the process preflight refuses to serve while they are bound. |
| `onprem` | `adapters/onprem/extraction.py` | `adapters/onprem/generation.py` | Fail-fast placeholders for a client-hosted extractor and model. They raise rather than pretending, which is what keeps the portability claim honest. |

## Remaining controls (TODO, repo owner)

- **Implement the two managed adapters, then their model id and version pinning** (P-07). The
  managed extraction and generation calls do not exist yet. When they do, pin the exact model id
  and version, record them here, and record them on the assessment alongside the policy `as_of`
  stamp so a figure and a narrative can each be traced to what produced them. Do not remove an
  entry from `INCOMPLETE_MANAGED_OPERATIONS` until the adapter executes the real call and an
  integration test proves the response mapping.
- **Prompt-injection screening through Hrz1** (rule R1). A claim file is adversary-supplied text:
  an FNOL narrative or an adjuster note is exactly where an instruction aimed at the extractor
  would be planted. Redaction is in place, screening is not, and no `GuardrailPort` is bound.
  Add one at the model boundary, screening input and output, and fail closed to
  deterministic-only when the screen is unavailable.
- **Budget, rate control and a kill switch** (P-10, P-11). No model call exists today, so nothing
  is metered. When one does: a per-request token budget, a per-tenant rate limit, timeouts and a
  circuit breaker on both model ports, and a switch that forces deterministic-only operation with
  the model disabled. The deterministic fallback already exists on the generation side; the
  switch that reaches for it deliberately does not.
- **A managed-profile eval run through the Hrz4 gate** (P-08, R5). The offline eval scores the
  deterministic pipeline against the golden oracle, which is evidence about the engines and not
  about a hosted model. Register the bundle `claims-integrity-investigator` with Hrz4, then
  add a managed-profile run that scores real extraction accuracy and narrative groundedness
  against the same golden claims.
- **Trace the model call to Hrz5** (rule R2). Spans today carry structural attributes only and no
  prompt or response record leaves the process. When a model is wired, the prompt and response
  record belongs in the shared sink with the same redaction discipline the audit write uses, not
  in a trace backend with a wider read audience.

Until these are complete, the system is safe to run offline: the deterministic engines plus the
deterministic offline extractor and narrator, on synthetic data, with every result routed to a
human. The managed model path is not production-cleared, and the repo enforces that rather than
merely saying it.
