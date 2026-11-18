# Substitution Test evidence, 2026-11-18

Tracking issue: Factory#1958. Questions are playbook Appendix C. Plan:
`plan/2026-11-18-1958-substitution-score.md`. Each fact says how it was read, so it can be
re-read. Nothing here changes branch protection, a cluster or a secret.

## Per-question state

| # | Question | State | Depends on |
|---|---|---|---|
| 1 | Context in AGENTS.md | Yes | none (Factory#3827, CFactory#553 merged) |
| 2 | Procedures as Agent Skills | Partial | skills over the three hub runbooks (below) |
| 3 | Tools via allowlisted MCP | Partial | a central reviewed allowlist (below) |
| 4 | Model calls via our gateway | No | #1959 (owner: Secret, egress, live checks, key rotation) |
| 5 | Routes, not model names | Partial | #1959, consumers preferring routes |
| 6 | Deterministic enforcement outside the agent | Yes | none |
| 7 | OTel normalised at a collector | No | #1959, a collector |
| 8 | Approval gates in CI/VCS | Partial | owner confirmation of the by-design exceptions (below) |
| 9 | Agent identity distinct from human | Partial | live proof of PFactory#1074 (fix deployed, no emit since) |
| 10 | Eval suite to qualify a model in a day | No | owner: runner and `BENCH_ENABLED` (#3713) |
| 11 | Artifact chain in our repos | Yes | none |
| 12 | Signed evidence trail for a production change | No | `Plan-Slug` trailer in the factory-gitops bump commit, live emit |

Sources for rows not read in the first pass (the evening re-score below re-read Q1, Q2, Q9 and Q12): Q4, Q5, Q7, Q9 and Q12 are carried from the
2026-11-18 re-score and the 2026-11-18 gap (a) comments on #1958 (live reads on the
k3d-factory cluster, not repeated here); Q6 from the issue body (review lenses, required
checks, Kyverno, cosign, Trivy; not re-read today); Q11 from `intent/`, `spec/`, `plan/` in
this repo and the registry rows named in #1958. The others are not re-verified.

Tally: 3 yes, 5 partial, 4 no. Below 10, so epic acceptance item 1 stays unticked.

## Q2: Agent Skill coverage

Read 2026-11-18 with `git ls-tree` on `origin/dev` (services) and `origin/main` (hub):

| Repo | `.claude/skills` | Other |
|---|---|---|
| AIFactory | 2 (+1 added by this work: `deployment-runbook`) | |
| PFactory | 10 (+1 added: `rbac-enforce-runbook`) | `companion-skills/` 2 |
| TFactory | 10 | `companion-skills/` 2, `docs/.well-known/skills/tfactory/SKILL.md` |
| CFactory | 0 | no runbook exists |
| Factory (hub) | 1 (`add-a-language`) | |

Runbooks found: AIFactory `guides/deployment/runbook.md`, PFactory
`docs/dev/rbac-enforce-runbook.md` (both now have a skill); hub
`docs/compliance/access-review-runbook.md`, `docs/compliance/dr-runbook.md`,
`docs/dev/benchmark-matrix-runbook.md` (no skill yet). TFactory and CFactory have no
runbook, so no skill was invented for them.

## Q3: MCP servers and where the allowlist is enforced

| Service | MCP configured | Selection and enforcement |
|---|---|---|
| AIFactory, PFactory, TFactory | `.mcp.json` names one first-party server each (`aifactory`, `pfactory`, `tfactory`); agent sessions add context7, playwright, graphiti, catalog servers by agent type | `apps/backend/agents/tools_pkg/models.py`: `AGENT_CONFIGS`, `get_required_mcp_servers`; `allowed_tools` from `get_allowed_tools` in `core/client.py` |
| same three | project config can add `CUSTOM_MCP_SERVERS` | AIFactory `core/client.py:986`, PFactory `:853`, TFactory `:899`; only servers in the agent's effective list are kept |
| same three | | the SDK option `permission_mode=bypassPermissions` (`core/client.py`) skips prompts, so the `allowed_tools` list is the gate for tool names; AIFactory also registers security hooks (`core/client.py:1098-1115`) that check commands separately. Not checked: PFactory and TFactory hooks |
| CFactory | no MCP client; serves `/mcp` | `apps/backend/cfactory/mcp.py`: per-tool key scope, unregistered tools default to write; no credential means denied unless `CFACTORY_MCP_DEV_OPEN=true`, which grants full scope (`mcp.py:1049-1050`, dev opt-in) |

Verdict: partial. Tool and server selection per agent type is in code and tested, but
there is no single reviewed allowlist for the family, and project config can add servers.
Not yes until one file lists permitted servers and tools and a check fails on drift.

## Q8: enforce_admins

Read 2026-11-18 with `gh api repos/olafkfreund/<repo>/branches/<branch>/protection/enforce_admins`:

| Repo | `main` | `dev` |
|---|---|---|
| Factory | true | no `dev` |
| AIFactory, PFactory, TFactory, CFactory | true | false |
| factory-gitops | false | no `dev` |

This matches the decision of 2026-10-22 (#943, option 2) in
`docs/compliance/branch-protection.md` (Phase 4): on for the five mains, off on every `dev`
for incident fixes and off on factory-gitops `main` because the CD bot pushes there. So the
earlier "false lets an admin merge past red" statement is stale for the mains.

Proposal, not applied (owner decision): keep as is; the by-design exceptions are the only
repos where it is false. Turning it on for a `dev` would remove
the incident-fix path; turning it on for factory-gitops would block the CD bot unless the
bot is moved to a PR flow. If the owner wants either, the route is
`scripts/apply_branch_protection.sh --apply --repo <R>` after editing the intent table, not
a manual change. The command that would enable it on one `dev` (printed, NOT run):

```
gh api -X POST repos/olafkfreund/<Repo>/branches/dev/protection/enforce_admins
```

Q8 stays partial until the owner accepts these exceptions as the design.

## Q10: eval suite

`.github/workflows/bench-nightly.yml` (Factory#3779) runs a 15-task SWE-bench subset
weekly with a USD budget enforced in code (#3713). The scheduled run happens only when the repo variable
`BENCH_ENABLED` is `true` (a manual `workflow_dispatch` always runs), on a self-hosted runner labelled `factory-bench`; `gh run list`
shows no run. Owner steps (`docs/benchmarks/nightly-eval.md`, "Owner steps to enable"): the
runner, the repo variables, agree the cost, run `workflow_dispatch` once, set
`BENCH_ENABLED`. Until a run has produced a scored result, the family cannot show a model
qualified in a day, so Q10 stays no.

## Re-score, 2026-11-18 evening (Factory#1958 closeout)

Read-only; slug `2026-11-18-1958-closeout`. Result: 3 yes, 5 partial, 4 no, unchanged in
total; Q1 is now a firm yes.

- Q1 Yes: `AGENTS.md` is at the root of Factory `main` and of AIFactory, PFactory, TFactory
  and CFactory `dev` (`git ls-tree origin/<base>`); Factory#3827 and CFactory#553 merged.
- Q2 Partial: `.claude/skills` on `origin/dev` now AIFactory 3 (`deployment-runbook`,
  AIFactory#2136), PFactory 11 (`rbac-enforce-runbook`, PFactory#1075), TFactory 10,
  CFactory 0; hub 1. No skill exists yet over the three hub runbooks, and TFactory and
  CFactory have no runbook to wrap.
- Q3 Partial: no central allowlist file or drift check has landed.
- Q9 Partial: PFactory#1076 (v0.8.7) fills `originator`, `agent_identity` and
  `autonomy_tier` at emit; the pod runs `sha-7b7325a`, which contains it. The registry's
  only schema-2 row (session 219) predates the fix and still shows nulls and
  `autonomy_tier: unknown`. Yes needs one emit after the deploy.
- Q12 No: no factory-gitops commit carries a `Plan-Slug` trailer
  (`git log origin/main | grep -c Plan-Slug` is 0), so the deploy-to-plan join cannot match.
- Q4, Q5, Q7 unchanged (gateway quota, failover and telemetry are code-complete in
  AIFactory#2138 but off, with no consumer routed). Q8 and Q10 unchanged: `enforce_admins`
  exceptions await owner acceptance; `bench-nightly.yml` has no run and no `BENCH_ENABLED`
  variable.

Remaining to reach 10: gateway live (Q4, Q5, Q7), bench runner (Q10), owner acceptance of
the branch-protection exceptions (Q8), the `Plan-Slug` bump and one live emit (Q12), one live emit (Q9), the allowlist (Q3).
