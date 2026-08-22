# FAQ index

Answers to the questions different teams ask when evaluating, adopting, or reviewing this
repository (Ins1, the Claims Integrity Investigator) as a common base for claims coverage and
fraud-indicator review. Each file is written for a specific audience; skim the one that matches
your role.

| FAQ | For | Answers |
|---|---|---|
| [security-faq.md](security-faq.md) | AppSec / security review | what the service processes, server-side identity and the exposure guard, redaction at every boundary, secrets, supply chain, audit tamper-evidence, what is out of scope |
| [portability-faq.md](portability-faq.md) | Architecture / cloud / exit planning | the no-lock-in claim and how it is tested, the three profiles, residency, the sovereign exit, data export |
| [features-faq.md](features-faq.md) | Product / claims and SIU owners | what the agent produces, what is deterministic vs what the model does, and the full "what this repo owns vs what it integrates" map |
| [adoption-faq.md](adoption-faq.md) | Engineering leads forking the repo | the rename, taking upstream fixes, the extension points, retuning the policy numbers, whether the demo and CI survive a fork |
| [compliance-faq.md](compliance-faq.md) | Compliance / model risk / privacy | autonomy and maker-checker, claimant PII, auditability, the model-risk story, residency enforcement, the regulator crosswalk |

These FAQs deliberately do **not** re-document capabilities owned by sibling catalog systems.
Where a concern belongs to another repo (the guardrail gateway Hrz1, the governed knowledge base
Hrz2, the agent registry Hrz3, the AI-quality gate Hrz4, observability and WORM audit Hrz5, the
human-review console Hrz7, the G1 to G5 financial-crime suite), the FAQ names the owning catalog
id and explains the boundary rather than duplicating it. See
[features-faq.md](features-faq.md) for the full map, and [`../ADOPTING.md`](../ADOPTING.md) for
the step-by-step fork guide.
