---
status: approved
issue: 1963
intent: intent/2026-10-24-1963-handoff-gate-survey.md
---

# Spec: survey the gate at each inter-agent handoff

## Design

One new page, `docs/dev/handoff-gate-survey.md`, in the style of `gate-honesty.md`. A summary table of the three handoffs (PFactory to AIFactory, AIFactory to TFactory, TFactory back to AIFactory), then one section each: the gate on the sending side, the gate on the receiving side, file:line at a pinned commit per repo, a verdict (gated / partial / ungated) and what the gate does not cover.
Where a handoff is not fully gated, a separate issue is filed in the owning repo and linked: TFactory#1427 (no contract verification at ingest), AIFactory#1858 (markdown-only handback skips validation).
Doc only; cites each repo's default branch.

## Alternatives rejected

Fix the gaps here: out of scope, code changes belong to their repos. Put the survey in #1963's comments: not durable or reviewable.

## Risks

Line numbers drift; the page pins commit SHAs and says so.

## Verification

Every cited line re-read with `git show <sha>:<path>`; the two filed issues exist.
