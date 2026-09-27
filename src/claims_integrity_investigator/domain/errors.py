"""Domain exceptions for the claims-integrity investigator.

Pure-Python exception hierarchy raised by the domain services. The domain layer never imports a
cloud SDK or a web framework; these errors let callers (the API, the CLI, the agent tool) react
to domain-level failures without coupling to any vendor SDK error type.
"""

from __future__ import annotations


class AssessmentError(Exception):
    """Base class for all domain-level errors this service raises."""


class GuardrailBlockedError(AssessmentError):
    """Raised when the guardrail refuses the claim file at extraction (rule R1).

    Extraction is the one model call an assessment cannot proceed without, so a refused claim
    file never yields a partial or substitute assessment: the service audits the attempt as
    ``Decision.BLOCKED`` and then raises this. The narration call is different by design: a
    refused narrative is audited BLOCKED too, but the assessment falls back to the deterministic
    template, because a disposition never waits on the model.
    """
