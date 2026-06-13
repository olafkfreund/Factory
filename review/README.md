---
title: Factory review stage — specialist agents + checklists
status: starter (vendored)
---

# Factory review stage

A **Review** stage for the PARR pipeline, seeded from
[`addyosmani/agent-skills`](https://github.com/addyosmani/agent-skills) (MIT).
PARR today is **Plan → Build → Verify** (PFactory → AIFactory → TFactory). This
adds the missing **Review** discipline: independent, persona-driven quality gates
that sit alongside TFactory's verify lanes and gate a build before it is
considered shippable.

## What's here

| Path | What | Maps to |
|---|---|---|
| `agents/code-reviewer.md` | Staff-engineer review persona (5-axis, ~100-line sizing) | a new TFactory review lane / CFactory gate |
| `agents/security-auditor.md` | OWASP Top-10 audit persona | TFactory `security` lane + our `security-checklist` |
| `agents/test-engineer.md` | QA persona — test pyramid, behaviour-not-implementation | TFactory `unit`/`api`/`mutation` lanes |
| `agents/web-performance-auditor.md` | Core Web Vitals audit, metric-honesty rules | frontend builds; CFactory RED metrics |
| `checklists/security-checklist.md` | OWASP / authn / secrets checklist | the verify `security` lane + our audit backlog |
| `checklists/testing-patterns.md` | Test pyramid (80/15/5), what to test | TFactory test-gen prompts |
| `checklists/performance-checklist.md` | profiling + Core Web Vitals | performance review |
| `UPSTREAM-LICENSE` / `.upstream-sha` | MIT license + pinned upstream commit | provenance |

## Provenance & license

These files are **vendored verbatim** from `addyosmani/agent-skills` at the commit
recorded in `.upstream-sha`, under the MIT License (`UPSTREAM-LICENSE`). They are a
**starting point** — adapt them to the factories (don't treat them as upstream we
must track). When we diverge, note it at the top of the changed file.

## How this becomes a real PARR stage (next)

1. **TFactory** already runs coverage/stability/mutation/lint/semantic lanes. Wire
   the `code-reviewer` + `security-auditor` personas as two additional verify
   lanes whose findings feed the same triager/verdict path.
2. The completion contract gains a `review` block (verdict per axis), gated by the
   **evidence rule** (see `Factory/docs/rfc/0001-*` evidence-gate addendum): a
   review lane cannot report "pass" without cited evidence.
3. CFactory surfaces the review axes next to the verify verdict in the cockpit.

See also: `Factory/docs/agents/red-flags.md` (the anti-rationalization blocks these
personas should carry) and the RFC-0001 evidence-gate addendum.
