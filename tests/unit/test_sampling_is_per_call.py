"""Sampling is decided per call: pinned where an output is compared, absent everywhere else.

History: on 2026-08-26 two identical runs against a deployment elsewhere in the fleet returned
different scores, because a shared request builder defaulted to ``temperature=0.2`` and every
grounded call sampled. The fix then was a ``0.0`` default on the request type. The owner's
decision of 2026-09-23 refines it: temperature is PINNED (``0.0``) only where the output is
extracted, classified, scored or compared against a deterministic check, and FREE for drafting,
summarising, narration, explanation and judging. Free means the parameter is ABSENT, not ``1.0``
and not a hidden default: some models (Opus 5, Fable 5) reject it outright.

Here the model only narrates. The recommendation, the indemnity and the fraud score are fixed by
the deterministic engine before the model is called, so the one model call samples freely and
the numbers it restates cannot move. **Temperature 0 is not a promise of determinism** either;
nothing here asserts one.
"""

from __future__ import annotations

from claims_integrity_investigator.domain.models import LlmRequest


def test_the_request_type_sends_no_temperature_unless_a_call_site_pins_one() -> None:
    """No hidden default: a value appears on the wire only when a call site chose it."""
    assert LlmRequest.__dataclass_fields__["temperature"].default is None
