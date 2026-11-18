---
status: approved
issue: 1958
intent: intent/2026-11-18-1958-substitution-score.md
---

# Spec: Substitution Test score, the agent-doable part

## Design

Decisions (owner delegation 2026-11-18, recommended option each time):

1. **Q1.** Add `AGENTS.md` at the root of the hub and CFactory as the maintained,
   self-contained context (what the repo is, layout, commands, gates, rules). The other
   three services carry an `AGENTS.md` that is a copy of an older `CLAUDE.md`; copies
   drift, so these are written from the current repo. In CFactory the content moves to
   `AGENTS.md` and `CLAUDE.md` becomes a one-line `@AGENTS.md` import, so one file is the
   source of truth. The hub gets `AGENTS.md` only (no `CLAUDE.md` exists). No secrets.
   Q1 scores yes once both are merged.
2. **Q2.** Coverage check, 2026-11-18: AIFactory 2 skills, PFactory 10 (+2 companion),
   TFactory 10 (+2 companion, +1 published at `docs/.well-known/skills/tfactory/SKILL.md`; counts are `.claude/skills`), CFactory 0, hub 1 (`add-a-language`). Runbooks that exist:
   AIFactory `guides/deployment/runbook.md`, PFactory `docs/dev/rbac-enforce-runbook.md`
   (TFactory and CFactory have none; hub has `docs/compliance/access-review-runbook.md`,
   `dr-runbook.md`, `docs/dev/benchmark-matrix-runbook.md`, not in scope here). Add one
   SKILL.md each to AIFactory and PFactory that points at the runbook and states its order
   of operations and stop points, copying no procedure text that is not in the runbook.
   Q2 stays partial: no skill for most procedures, and there is no hub-wide inventory.
3. **Q3.** Record, in `docs/compliance/substitution-test-2026-11-18.md`, which MCP servers
   each service configures and where an allowlist is enforced. Findings: AIFactory,
   PFactory and TFactory pick servers and tools per agent type in
   `apps/backend/agents/tools_pkg/models.py` (`AGENT_CONFIGS`, `get_required_mcp_servers`)
   and build `allowed_tools` in `core/client.py`; sessions run with
   `permission_mode=bypassPermissions`; all three also admit `CUSTOM_MCP_SERVERS` from
   project config (AIFactory `core/client.py:986`, PFactory `:853`, TFactory `:899`). The
   repo `.mcp.json` of each of the three names one first-party server. CFactory configures
   no MCP client; it serves `/mcp` (read tools plus board write tools that can dispatch
   work), enforced per tool by key scope, unregistered tools defaulting to write, and
   denied when no credential is configured (`apps/backend/cfactory/mcp.py`). There is no central, reviewed
   allowlist across the family, so Q3 is partial, not yes.
4. **Q8.** Record `enforce_admins` per repo and branch (read-only, 2026-11-18):
   Factory `main` true; AIFactory, PFactory, TFactory, CFactory `main` true and `dev` false;
   factory-gitops `main` false (no `dev`). Proposal only: set it on the `dev` branches and
   on factory-gitops `main` once the owner confirms no release step relies on an admin
   bypass; the command is in the evidence doc, not run. Q8 stays partial.
5. **Q10.** Assess, do not presume. `.github/workflows/bench-nightly.yml` runs a 15-task
   subset weekly, only when `BENCH_ENABLED` is `true`, on a self-hosted `factory-bench`
   runner the owner provides (#3713, #3779). Until it has run, the family cannot show a
   model qualified in a day. Q10 stays no; blockers listed.
6. **Comment.** Post one per-question table on #1958 with the evidence doc linked, each
   question marked as waiting on owner steps, #1959 (Q4, Q5, Q7), PFactory signature
   identity (Q9, Q12) or on a team. Tick acceptance item 1 only if 10+ with evidence.

## Alternatives rejected

- Byte-copying the services' `AGENTS.md`: they describe other repos and are stale.
- Symlinking `AGENTS.md` to `CLAUDE.md`: breaks on tools that read files without
  following links, and CFactory's `CLAUDE.md` says "Claude Code".
- Writing skills for every runbook: out of scope; the hub runbooks belong to other teams.
- Enabling `enforce_admins` now: owner decision; could block the dev to main promotion.
- Scoring Q3 or Q10 yes on existence of a config or workflow: dishonest.

## Risks

- Evidence goes stale; the doc is dated and says how each fact was read.
- A skill could be read as authority to run a cluster install: each says the install needs
  the operator and stops where the runbook says so.

## Verification

- Hub: `pytest` markdown/link checks if present, `git diff --check`; CI on each PR.
- Skills: frontmatter parses (name, description); the cited runbook paths exist.
- Every cited path and line in the evidence doc is re-opened by the reviewer.
- Codex reviews each draft and the final diff.
