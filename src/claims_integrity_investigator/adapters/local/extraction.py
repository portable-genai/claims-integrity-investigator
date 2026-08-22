"""Local ExtractionPort: a deterministic parser over the claim-file marker grammar (SDK-free).

The managed adapter is Document AI plus Gemini multimodal; this offline stand-in parses the
compact ``META`` / ``SCHED`` / ``LINE`` markers the fixtures carry and gathers adjuster-note
prose. It is pure and deterministic, so the gate and demo extract the same evidence every run.
It reads whatever text it is handed, which is why the orchestrator redacts BEFORE calling it:
the guarantee that no raw identifier reaches an extraction model must not depend on this
adapter happening to ignore free text.
"""

from __future__ import annotations

import re

from ...config import Settings
from ...domain.models import (
    ClaimLine,
    DocumentKind,
    ExtractedClaim,
    PolicyItem,
    RawClaimFile,
)

_META_RE = re.compile(r"META\s+loss=(\S+)\s+notified=(\S+)")
_SCHED_RE = re.compile(
    r"SCHED\s+category=(\S+)\s+included=(true|false)\s+excess=(\d+)\s+"
    r"sublimit=(\d*)\s+exclusion=(\S*)"
)
_LINE_RE = re.compile(
    r"LINE\s+id=(\S+)\s+category=(\S+)\s+desc=(.*?)\s+cents=(\d+)\s+"
    r"invoice=(\S*)\s+date=(\S*)\s+doc=(\S+)"
)


class LocalExtractionAdapter:
    """Parse a raw claim file into structured evidence deterministically."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def extract(self, claim_file: RawClaimFile) -> ExtractedClaim:
        loss_date = ""
        notified_date = ""
        lines: list[ClaimLine] = []
        schedule: list[PolicyItem] = []
        notes: list[str] = []

        for document in claim_file.documents:
            text = document.text
            meta = _META_RE.search(text)
            if meta:
                loss_date, notified_date = meta.group(1), meta.group(2)
            for match in _SCHED_RE.finditer(text):
                schedule.append(_policy_item(match))
            for match in _LINE_RE.finditer(text):
                lines.append(_claim_line(match))
            if document.kind is DocumentKind.ADJUSTER_NOTE:
                notes.append(text)

        return ExtractedClaim(
            claim_id=claim_file.claim_id,
            subject=claim_file.subject,
            policy_ref=claim_file.policy_ref,
            loss_date=loss_date,
            notified_date=notified_date,
            lines=tuple(lines),
            schedule=tuple(schedule),
            adjuster_notes="\n".join(notes),
        )


def _policy_item(match: re.Match[str]) -> PolicyItem:
    sublimit = match.group(4)
    return PolicyItem(
        category=match.group(1),
        included=match.group(2) == "true",
        excess_cents=int(match.group(3)),
        sub_limit_cents=int(sublimit) if sublimit else None,
        exclusion_clause=match.group(5),
    )


def _claim_line(match: re.Match[str]) -> ClaimLine:
    return ClaimLine(
        line_id=match.group(1),
        category=match.group(2),
        description=match.group(3).strip(),
        claimed_cents=int(match.group(4)),
        invoice_no=match.group(5),
        invoice_date=match.group(6),
        doc_ref=match.group(7),
    )
