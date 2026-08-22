"""Tool functions an agent runtime calls: thin, side-effect-honest wrappers on the services.

Design rules, in the order they matter:

* **No business logic here.** The domain service decides HOW; the model only decides WHICH tool
  to call. A rule that lives in a tool wrapper is a rule the CLI and the API do not have.
* **Rule R8 applies on this path too.** An escalated result is ROUTED from inside the tool, in
  the same call that produced it. An agent surface that only returned the flag would be a third
  place an escalation can quietly stop, after the API and the CLI.
* **Import-safe without a runtime.** ``google.adk`` is imported lazily inside
  :func:`build_function_tools`, so these callables are importable, testable and runnable with
  no ADK and no cloud SDK installed.
* **Typed and documented.** A runtime derives each tool's name, description and JSON parameter
  schema from the signature and the docstring, so both are part of the contract.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from hex_service_kit.serialization import to_jsonable
from pii_kit import redact

from ..config import Container, Settings, build_container
from ..domain.assessment_service import build_assessment_service
from ..domain.pii import PII_PATTERNS

if TYPE_CHECKING:  # pragma: no cover - typing only, never imported at runtime
    from google.adk.tools import FunctionTool

#: The identity a tool call is attributed to when the runtime propagates none. It names the
#: SERVICE, not a person, so an unattributed action is never mistaken for a human's.
DEFAULT_ACTOR = "claims-integrity-investigator-agent"


def _container(settings: Settings | None) -> Container:
    return build_container(settings)


def _redacted(node: Any) -> Any:
    """Mask personal data in every string of a tool result, however deeply it is nested.

    A tool result is not an API response. The API returns to the authenticated caller the text
    that caller just submitted; a TOOL result goes into a model's context, and P-04 says
    minimise the data that reaches a model. The evidence snippet a caller may legitimately read
    back is therefore masked here, on the way to the agent, using the same pattern pack the
    audit write masks with. Walking the whole structure rather than three named fields means a
    future field cannot arrive unredacted just because nobody remembered to add it.
    """
    if isinstance(node, str):
        return redact(node, PII_PATTERNS)
    if isinstance(node, dict):
        return {key: _redacted(value) for key, value in node.items()}
    if isinstance(node, list):
        return [_redacted(value) for value in node]
    return node


def assess_claim(
    claim_id: str,
    actor: str = DEFAULT_ACTOR,
    tenant: str = "",
    settings: Settings | None = None,
) -> dict[str, Any]:
    """Assess one claim and route it for human review.

    Fetches the claim file, redacts before extraction, runs the deterministic coverage and
    red-flag engines, drafts the cited narrative, writes an already-redacted audit event, and
    ROUTES the assessment to the human-review console (rule R8). Every assessment is
    consequential, so it always routes.

    Args:
      claim_id: The claim to assess.
      actor: The verified identity this call is attributed to.
      tenant: The tenant whose claim to read, and the partition asserted on the outbound
        review. Empty falls back to the configured tenant. A claim id is a name, not an
        entitlement, and this tool is the widest read surface in the repo: the MODEL chooses
        the argument, so the scope is not the tool's to widen.

    Returns:
      A JSON-safe result dict with every string masked for personal data (P-04: a tool result
      goes into a model's context), plus ``review_ref``: where the escalation WENT, so a caller
      can confirm the escalation was routed and not merely flagged.
    """
    container = _container(settings)
    scope = tenant or container.settings.tenant
    result = build_assessment_service(container).assess(claim_id, actor=actor, tenant=scope)
    review_ref = container.review_router.route(result, maker=actor, tenant=tenant)
    payload = _redacted(to_jsonable(result))
    if not isinstance(payload, dict):  # pragma: no cover - dataclasses serialise to objects
        raise TypeError("a claim assessment must serialise to a JSON object")
    # Attached after the redaction pass: it is a routing reference, not narrative text, and
    # masking an identifier would break the caller's ability to look the review up.
    payload["review_ref"] = review_ref
    return payload


def list_siu_queue(tenant: str = "", settings: Settings | None = None) -> dict[str, Any]:
    """List one tenant's claims currently routed to human review (the SIU / investigate queue).

    Reads the review router's pending queue (the local outbox offline) and returns the items a
    reviewer still owns. It manufactures nothing: an empty queue is the honest answer when
    nothing has been routed in this process.

    Args:
      tenant: The tenant whose queue to list. Empty falls back to the configured tenant, and a
        tenant that owns nothing lists nothing: an unscoped queue is the read-by-id defect with
        no id left to guess.

    Returns:
      A dict with ``count`` and ``items`` (claim id, subject, recommendation and severity per
      queued review), every string masked for personal data.
    """
    container = _container(settings)
    scope = tenant or container.settings.tenant
    router = container.review_router
    pending = getattr(router, "outbox", None)
    items: list[dict[str, str]] = []
    if pending is not None:
        for entry in pending.pending():
            review = entry.review
            if review.tenant != scope:
                continue
            items.append(
                {
                    "claim_id": review.case_ref,
                    "subject": review.subject,
                    "recommendation": review.source_key.rsplit(":", 1)[-1],
                    "severity": review.severity,
                }
            )
    payload = {"count": len(items), "items": items}
    redacted = _redacted(payload)
    assert isinstance(redacted, dict)
    return redacted


def verify_audit_trail(settings: Settings | None = None) -> dict[str, Any]:
    """Verify the audit trail's hash chain and its external head anchor.

    Returns:
      A dict with ``ok``, the record counts and a ``detail`` string. ``ok`` is false for an
      edited, deleted or reordered record, and, when an external anchor is configured, for a
      truncated tail as well. Without an anchor a truncation cannot be detected, and the detail
      says so rather than implying a stronger guarantee than the store provides.
    """
    resolved = settings or Settings.load()
    audit = _container(resolved).audit
    verify = getattr(audit, "verify", None)
    if verify is None:
        raise NotImplementedError(
            f"the {resolved.profile} audit adapter does not expose chain verification; a "
            "managed WORM sink is verified by its own retention policy, not from here"
        )
    report = verify()
    return {
        "ok": report.ok,
        "entries": report.entries,
        "chained": report.chained,
        "legacy": report.legacy,
        "first_bad_seq": report.first_bad_seq,
        "detail": report.detail,
        "anchored": bool(resolved.audit_anchor_path),
    }


#: The tool table. The agent card advertises exactly these, by function name.
TOOL_FUNCTIONS = (assess_claim, list_siu_queue, verify_audit_trail)


def build_function_tools() -> list[FunctionTool]:
    """Wrap each callable as a runtime FunctionTool (the only ADK-dependent code path).

    The import is deliberately here rather than at module scope: without it this module, the
    card and every tool would need an agent runtime installed to be imported at all, and the
    offline gate installs none.
    """
    # No ignore comment: the missing-import error for this module is already reported (and
    # ignored) at the TYPE_CHECKING import above, and a second one would be flagged as unused.
    from google.adk.tools import FunctionTool

    return [FunctionTool(func=function) for function in TOOL_FUNCTIONS]
