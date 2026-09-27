"""GuardrailPort: the boundary that screens a generation call in both directions (rule R1).

Rule R1 is the reason this port exists: this service binds `agent-guardrail-gateway` as a
mandatory dependency (`config/settings.yaml`'s dependency list; see COMPLIANCE.md), which means
every model call's input must be screened BEFORE it reaches the model, and its output AFTER it is
produced and BEFORE it is used or audited. ``domain/assessment_service.py`` screens the
extraction call and ``domain/drafting.py`` the narration call, each in exactly that shape.

The domain stays pure. This port names the screen; the adapters (not this module) depend on the
managed guardrail service (Model Armor) or a local heuristic stand-in.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from ..domain.kernel import Direction, GuardrailVerdict


@runtime_checkable
class GuardrailPort(Protocol):
    def screen(self, text: str, direction: Direction) -> GuardrailVerdict:
        """Screen inbound prompt or outbound response text; may sanitise it.

        Never raises on a policy match: a block is reported as ``GuardrailVerdict(allowed=False,
        ...)`` so the caller can audit the attempt before deciding how to fail. An allowed verdict
        carries ``sanitized_text``, the text the caller uses from then on EXACTLY as given (the
        input unchanged when nothing was redacted, possibly empty when everything was); the
        caller never falls back to the unscreened original.

        Raising is reserved for the adapter being unable to decide at all: its backend errored
        or timed out, no template is configured, or the on-prem placeholder is bound. The domain
        treats every such raise as a refusal (fail closed) and audits it.
        """
        ...
