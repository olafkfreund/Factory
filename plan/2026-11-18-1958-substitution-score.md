---
status: draft
issue: 1958
spec: spec/2026-11-18-1958-substitution-score.md
coders:
  1: codex   # contained mechanical move in CFactory
  2: codex   # one new SKILL.md from an existing runbook, AIFactory
  3: codex   # one new SKILL.md from an existing runbook, PFactory
  4: coder   # lead writes the hub AGENTS.md (needs hub knowledge)
  5: coder   # lead writes the evidence doc (needs the verified facts)
reviewers:
  - codex    # independent read-only review of each draft and the final diff
---

# Plan: Substitution Test score, the agent-doable part

Carries the approved spec. Four PRs: hub (artifacts, `AGENTS.md`, evidence doc; base
`main`), CFactory, AIFactory, PFactory (base `dev`). Nothing runs against a cluster;
branch protection is not changed. Q1 scores yes when the hub and CFactory PRs merge. Q2,
Q3, Q8 stay partial, Q10 stays no; Q4, Q5, Q7 wait on #1959, Q9, Q12 on PFactory
signature identity. The score does not reach 10, so acceptance item 1 stays unticked.

## Steps

1. CFactory worktree off `origin/dev`: `mv CLAUDE.md AGENTS.md` (filesystem move, no
   git staging by the implementer), then write `CLAUDE.md` as the single line
   `@AGENTS.md`. Change the heading "# CLAUDE.md" to "# AGENTS.md". Update every tracked
   reader-facing link to `CLAUDE.md` (`git grep -n "CLAUDE.md"`, known: `SUPPORT.md:9`) to
   `AGENTS.md`. Check: the lead stages named paths, then `git diff --cached -M --stat`
   shows a rename plus a 1-line `CLAUDE.md`.
   Traps: lead stages and commits; no emojis; `docs/` is the public Jekyll site, do not touch.
2. AIFactory worktree off `origin/dev`: add `.claude/skills/deployment-runbook/SKILL.md`
   (frontmatter `name`, `description`, `when_to_use` like the sibling `handover` skill),
   pointing at `guides/deployment/runbook.md`: pre-flight checklist, KMS backend choice,
   install, verification gate, troubleshooting; says an agent never runs `helm install`
   against a live cluster without the operator. No text beyond what the runbook says.
   Check: frontmatter parses (`python -c` yaml.safe_load on the block); the cited path
   exists. Traps: AIFactory generated autonomy matrix is not touched; no secrets.
3. PFactory worktree off `origin/dev`: add `.claude/skills/rbac-enforce-runbook/SKILL.md`
   pointing at `docs/dev/rbac-enforce-runbook.md`: the legacy-key count queries
   (aggregate only), the ordered steps 1 to 4 before flipping
   `RBAC_ENFORCE_TASK_ROUTES`, and that the flip and SQL deletes are the operator's.
   Same checks as step 2.
4. Hub: `AGENTS.md` at the root: what the repo is, layout (`intent/ spec/ plan/`,
   `standards/`, `apis/`, `docs/`, `contracts/`, `shared/`, `scripts/`), the artifact
   workflow gates, branching (`main`), rules with teeth read from `README.md` and
   `standards/`, no secrets. Check: every path it names exists (`test -e`).
5. Hub: `docs/compliance/substitution-test-2026-11-18.md`: per-question table, Q2 coverage
   counts, Q3 MCP inventory with file:line, Q8 table plus the `gh api` command that would
   set `enforce_admins` (not run), Q10 blockers, a "how read" line per fact. Check: each
   cited path exists on the stated branch; `git diff --check`.
   Facts to carry (read 2026-11-18, `gh api .../branches/<b>/protection/enforce_admins`):
   `enforce_admins` true on Factory `main`, and on `main` of AIFactory, PFactory, TFactory,
   CFactory; false on `dev` of those four; false on factory-gitops `main`; Factory and
   factory-gitops have no `dev`. Skill counts (`.claude/skills`): AIFactory 2, PFactory 10
   (+2 companion-skills), TFactory 10 (+2 companion, +1 `docs/.well-known/skills/tfactory`),
   CFactory 0, hub 1. MCP: AIFactory/PFactory/TFactory select servers per agent type in
   `apps/backend/agents/tools_pkg/models.py` (`AGENT_CONFIGS`, `get_required_mcp_servers`),
   `allowed_tools` in `core/client.py`, `permission_mode=bypassPermissions`, and admit
   `CUSTOM_MCP_SERVERS` (AIFactory `core/client.py:986`, PFactory `:853`, TFactory `:899`);
   CFactory serves `/mcp` with per-tool key scopes (`apps/backend/cfactory/mcp.py`),
   unregistered tools default to write, no credential means denied. Q10: workflow
   `.github/workflows/bench-nightly.yml` runs only when `BENCH_ENABLED` is `true` on a
   self-hosted `factory-bench` runner; no run recorded.
6. After the hub PR opens: post the per-question comment on #1958 linking the evidence doc
   and the four PRs; record the "Decision (owner delegation 2026-11-18):" comment.

## Tests

- Hub: `git diff --check`; the repo's markdown or docs tests if CI runs any
  (`.github/workflows`), run locally where they exist.
- CFactory: `PYTHONPATH=apps/backend pytest -q -x` is unaffected by a docs rename; CI
  must stay green on the head SHA.
- Services: CI green on the head SHA; `codex review --base origin/<base>` per repo.

## Rollback

Revert each PR; docs and skill files only, nothing is deployed.
