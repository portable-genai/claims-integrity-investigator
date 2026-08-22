"""Minimal stdlib CLI: assess a claim, or verify the audit chain (argparse, no extra deps).

The ``assess`` command prints the coverage arithmetic line by line and the red flags with their
reasons, so a presenter can see that every figure is the deterministic engine's, then routes the
assessment to human review (rule R8) on this path too.
"""

from __future__ import annotations

import argparse
import sys

from hex_service_kit.logging import configure_logging

from ..config import build_container
from ..domain.assessment_service import build_assessment_service
from ..domain.models import money


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="claims_integrity_investigator")
    sub = parser.add_subparsers(dest="command", required=True)

    assess_cmd = sub.add_parser("assess", help="Assess a single claim by id.")
    assess_cmd.add_argument("claim_id")
    assess_cmd.add_argument("--actor", default="cli-user@bank.example")
    assess_cmd.add_argument(
        "--tenant",
        default="",
        help="Tenant whose claim to read, and the partition asserted to Hrz7.",
    )

    args = parser.parse_args(argv)
    container = build_container()
    # Idempotent: a process that is both an API app and a CLI configures once.
    configure_logging(container.settings.profile, service="claims-integrity-investigator")

    if args.command == "assess":
        service = build_assessment_service(container)
        tenant = args.tenant or container.settings.tenant
        result = service.assess(args.claim_id, actor=args.actor, tenant=tenant)
        print(f"{result.claim_id} ({result.subject}) policy {result.policy_ref}")
        print(f"  recommendation: {result.recommendation.value} [{result.severity.value}]")
        print("  coverage:")
        for line in result.coverage.lines:
            print(
                f"    - {line.line_id} {line.category}: {line.status.value}, "
                f"pay {money(line.indemnity_cents)} of {money(line.claimed_cents)} "
                f"({line.reason})"
            )
        print(f"  indemnity quantum: {result.indemnity}")
        print(f"  fraud score: {result.red_flags.fraud_score}")
        for flag in result.red_flags.flags:
            print(f"    ! {flag.kind.value} (+{flag.uplift}): {flag.reason}")
        print(f"  requires_human_review: {result.requires_human_review}")
        # Rule R8 on the CLI path too: the same escalation, the same router. A surface that only
        # printed the flag would be a second place for an escalation to stop.
        ref = container.review_router.route(result, maker=args.actor, tenant=args.tenant)
        print(f"  routed to human review: {ref}")
        return 0

    return 2  # pragma: no cover - argparse requires a subcommand


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main(sys.argv[1:]))
