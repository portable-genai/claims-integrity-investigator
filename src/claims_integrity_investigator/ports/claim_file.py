"""ClaimFilePort: fetch one claim file as raw, cited documents. It computes nothing.

The boundary to the claim-document store (FNOL, adjuster notes, invoices, medical and repair
reports, photos). The adapter returns raw document rows with stable locators so every later
figure can be cited back to a document; it never parses amounts or decides cover.

**Every read is tenant-scoped, and the tenant is a required argument.** This port took a claim id
and nothing else, so an authenticated caller from any tenant who named an id received that
claimant's whole file and had it assessed under their own tenant. Object-level authorization
cannot live at the call site, because there are several of them and only one has to forget;
making ``tenant`` a keyword-only parameter of the protocol means a caller with no tenant to pass
does not compile rather than silently reading everything.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from ..domain.models import RawClaimFile


@runtime_checkable
class ClaimFilePort(Protocol):
    def fetch(self, claim_id: str, *, tenant: str) -> RawClaimFile:
        """Return ``tenant``'s raw claim file for ``claim_id`` (raw documents, no interpretation).

        Raises ``KeyError`` when the store has no such file FOR THAT TENANT. A file owned by
        another tenant is indistinguishable from one that does not exist, deliberately:
        answering "exists, but not for you" tells the caller the id is real somewhere.
        """
        ...
