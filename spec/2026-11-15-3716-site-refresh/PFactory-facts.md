# PFactory: what shipped, 2026-08-10 to 2026-11-15

Sources: GitHub release notes v0.6.17..v0.6.42 (`gh release`), `gh pr view`, and PFactory source on `dev` (read via `gh api`). Read-only. Release link pattern: https://github.com/olafkfreund/PFactory/releases/tag/<tag>. PR links: https://github.com/olafkfreund/PFactory/pull/<n>.

## Current version
- Latest release: **v0.6.42, 2026-10-31** (published 13:55 UTC). https://github.com/olafkfreund/PFactory/releases/tag/v0.6.42
- First release inside the window: v0.6.17, 2026-09-03. Nothing was tagged 2026-08-10 to 2026-09-02 (previous tag v0.6.16 is 2026-06-11). 26 releases in the window.
- No release between 2026-10-31 and 2026-11-15. `dev` is 9 commits ahead of `main` (see last section).
- Caveat: v0.6.19 (2026-09-18) bundles items its notes call "previously unversioned on main", so some of that work is older than the tag date.

## What PFactory is today (3 sentences)
PFactory is the planning stage of the Factory line: it turns a request (a docx, pdf, markdown, Gherkin or EARS document, or a labelled GitHub issue) into a reviewed plan, checks it with a set of review lenses and a hard readiness gate, and waits for human approval. After approval it emits an HMAC-signed Task Contract plus governed GitHub epics and issues, which AIFactory builds and TFactory verifies (README.md "The planning pipeline"). Since September it also runs as several replicas on a shared Postgres store, with org-scoped access control (mostly in shadow mode) and runtime invariant checks.

## Stage and lens counts (verified against `dev`)
- **Review lenses: 7 today.** Six mandatory lenses always run: feasibility, architecture, security, compliance, best-practices, completeness. `apps/backend/plan/review/lenses/base.py:71-78`. A seventh, `red-team`, is added when the extension registry enables it: `base.py:86-89`. The registry entry `red-team-review` has `"enabled": true`: `apps/backend/plan/emit/contracts/extension-registry.json:32-37`. The compliance lens is `"mandatory": true`: same file, lines 39-47. Lens names are set in each lens module (e.g. `lenses/compliance.py:495`, `lenses/red_team.py:110`).
- **Public docs are stale on this.** README.md line 59 and `docs/planning-and-trust.md:59` still say "architecture / security / best-practice / feasibility" (4 lenses, plus Red Team in the docs page). Do not copy that.
- **Gate count: no single number in code.** Beyond the lenses there is a hard readiness gate (`apps/backend/plan/review/gates.py`, `run_gates` at line 54) and the extension registry lists 4 optional gates, standards-conformance, verification (VAL), ci-gated-auto-merge and concurrency-budget-admission, among 24 registry entries (intake, plan, review, gate, runtime, connector, observe). Use "7 review lenses plus a hard readiness gate", not a bare "N gates".
- **Pipeline stages: the code has no canonical stage count.** Three sources disagree by design, so pick one and say which:
  - Homepage diagram (`docs/_includes/pipeline-diagram.html:9-67`): **5 steps**: Ingest, Enrich, Decompose, Review & approve, Emit. This is the one that matches the current site.
  - README mermaid (`README.md:55-64`): 9 nodes (Request, Ingest, Enrich, Decompose, Feasibility, Review lenses, Hard readiness gate, Human approval, Emit).
  - `PlanService.process()` (`apps/backend/plan/service.py:1285-1331`): detect and plan-type, decompose, synthesize, review gates. The board has 5 columns (`service_helpers.py:41`, `87-100`).
  - Recommendation: say "five stages" only if you mean the homepage diagram; otherwise avoid a number.

## Shipped, by theme

### 1. Runs as several replicas on a shared store
- Plan sessions are shared across replicas through a Postgres store, with atomic id allocation, one emit per session (a second concurrent emit gets 409), and compare-and-set writes. v0.6.20 · [#755](https://github.com/olafkfreund/PFactory/pull/755) [#757](https://github.com/olafkfreund/PFactory/pull/757) [#758](https://github.com/olafkfreund/PFactory/pull/758) [#771](https://github.com/olafkfreund/PFactory/pull/771) · https://github.com/olafkfreund/PFactory/releases/tag/v0.6.20
- A pod that migrates on boot now uses the shared session store and the durable job-state store without a restart. v0.6.21, v0.6.22 · #774 #777 · https://github.com/olafkfreund/PFactory/releases/tag/v0.6.21 · https://github.com/olafkfreund/PFactory/releases/tag/v0.6.22
- Running tasks, insights replies, changelogs and PR reviews are tracked in a shared `run_leases` table, so a duplicate start gets 409 and a stop reaches the owning replica. v0.6.25 · #805 · https://github.com/olafkfreund/PFactory/releases/tag/v0.6.25
- Email OAuth connect state is stored in the database so any replica can complete the callback; the portal's GitHub CLI sign-in refuses when more than one replica may run. v0.6.24 · #807 · https://github.com/olafkfreund/PFactory/releases/tag/v0.6.24
- WebSocket events are relayed between pods through Postgres. v0.6.30 · #804 #833 · https://github.com/olafkfreund/PFactory/releases/tag/v0.6.30
- Task logs and board status/phase/progress live in Postgres so any replica can serve them (task logs pruned after `PFACTORY_TASK_LOG_RETENTION_DAYS`, default 90). v0.6.31 · #829 #904 #905 #908 · https://github.com/olafkfreund/PFactory/releases/tag/v0.6.31
- Insights chat sessions are read from the shared volume instead of a per-pod cache. v0.6.32 · #912 #913 · https://github.com/olafkfreund/PFactory/releases/tag/v0.6.32
- Drain support for rolling deploys: `GET /api/drain` reports whether a pod holds a run or a running agent process, and the Helm chart ships a preStop drain, behind `drain.enabled`. v0.6.33, v0.6.34 · #920 #922 #924 · https://github.com/olafkfreund/PFactory/releases/tag/v0.6.34
- Postgres connection pools are capped per pod (at most 19 connections, was 38), and boot migrations take a Postgres advisory lock so pods that start together apply each revision once. v0.6.40, v0.6.42 · #964 #982 · https://github.com/olafkfreund/PFactory/releases/tag/v0.6.40 · https://github.com/olafkfreund/PFactory/releases/tag/v0.6.42
- Note: v0.6.20 says the KEDA one-replica pin stays in place and lifting it is a separate step. Do not claim autoscaled multi-replica production from these notes.

### 2. Org-scoped access control
- Plan session reads are scoped to the caller's org (enforced for org-scoped `acw_` API keys; human viewers in shadow mode). Adds migration `e5b8c3f1a9d7`. v0.6.41 · #976 · https://github.com/olafkfreund/PFactory/releases/tag/v0.6.41
- Plan session writes (process, approve, waive, reject, discard, emit, and the MCP proxies) return 404 for another org's session. Same split: enforced for org-scoped keys, shadow mode for humans. v0.6.42 · #985 · https://github.com/olafkfreund/PFactory/releases/tag/v0.6.42
- Org role checks on 39 task and plan-pipeline write routes, in **shadow mode**: a would-be denial is logged and audited but responses do not change, until `RBAC_ENFORCE_TASK_ROUTES` (default off) is set. Extended to more routes in v0.6.39. v0.6.38, v0.6.39 · #950 #957 · https://github.com/olafkfreund/PFactory/releases/tag/v0.6.38 · https://github.com/olafkfreund/PFactory/releases/tag/v0.6.39
- `acw_` API key scopes are capped by the owner's current org role, so a removed or demoted owner loses access through their keys; `acw_` keys now authenticate on the MCP paths (they failed with a 500 before). v0.6.37, v0.6.38 · #938 #945 · https://github.com/olafkfreund/PFactory/releases/tag/v0.6.37 · https://github.com/olafkfreund/PFactory/releases/tag/v0.6.38
- Remote MCP checks the calling key per tool call (viewer for read, member for write). It is off unless `PFACTORY_MCP_REMOTE_ENABLED` is set. Read paths of the stdio MCP proxies and the agent console also check roles. v0.6.40 · #966 #967 · https://github.com/olafkfreund/PFactory/releases/tag/v0.6.40
- `GET /api/audit/export` now needs org admin. v0.6.37 · #942 · https://github.com/olafkfreund/PFactory/releases/tag/v0.6.37
- Worktree endpoints now need `project_id:spec_id` (a bare spec id gets 400), which also fixed the web UI's merge preview. v0.6.40 to v0.6.42 · #974 #966 #984 · https://github.com/olafkfreund/PFactory/releases/tag/v0.6.41
- Runbook for turning enforcement on: `docs/dev/rbac-enforce-runbook.md`. v0.6.41 · #972 · https://github.com/olafkfreund/PFactory/releases/tag/v0.6.41

### 3. Security hardening
- The command allowlist now parses shell grammar (bashlex AST), so a command nested in `$(...)`, backticks or a pipe is checked; the old regex missed them. `PFACTORY_STRICT_COMMAND_PARSING=1` fails closed. v0.6.17 · #133 · https://github.com/olafkfreund/PFactory/releases/tag/v0.6.17
- Fail closed on exposure: `/mcp` returns 401 when `PFACTORY_MCP_SECRET` is unset outside dev, CORS rejects wildcard origins with credentials, and the server refuses to boot with `DISABLE_AUTH` on a non-loopback host. v0.6.17 · #131 · https://github.com/olafkfreund/PFactory/releases/tag/v0.6.17
- The Copilot plan-review workflow no longer trusts a `[bot]` name suffix (CVE-2025-66032 pattern). v0.6.17 · #131 · https://github.com/olafkfreund/PFactory/releases/tag/v0.6.17
- OIDC ID tokens are checked against PFactory's own config (issuer, audience, `exp`, asymmetric signature only). Azure AD v1 issuers must move to v2.0. v0.6.39 · #956 · https://github.com/olafkfreund/PFactory/releases/tag/v0.6.39
- Two critical findings (command injection, SSRF) closed with barrier-aware analysis; a credentialed git argv no longer reaches log files. v0.6.19 · #505 #517 #599 · https://github.com/olafkfreund/PFactory/releases/tag/v0.6.19
- CVE gates cleared in the image and dependencies: CVE-2026-111497 and undici (v0.6.33, #918), curl and ca-certificates (v0.6.29, #879), Authlib CVE-2026-96760 (v0.6.39, #952), joserfc CVE-2026-119283 (v0.6.41, #973; notes say not reachable), uv CVE-2026-111943 (v0.6.42, #983). Each failed the Trivy P0 gate. https://github.com/olafkfreund/PFactory/releases/tag/v0.6.42
- The image's Node comes from the official `node:26` image so it cannot outrun glibc (a glibc mismatch broke every PR on 2026-09-03). v0.6.19 · #732 · https://github.com/olafkfreund/PFactory/releases/tag/v0.6.19

### 4. Plan review quality
- A plan whose worked example contradicts its own invariant is blocked. v0.6.19 · #402 · https://github.com/olafkfreund/PFactory/releases/tag/v0.6.19
- Plan review publishes the per-lens verdict, not only `gates_passed`, so the cockpit can name the lens that blocked a plan. v0.6.19 · CFactory#245 · https://github.com/olafkfreund/PFactory/releases/tag/v0.6.19
- The compliance lens is marked mandatory in the registry and cannot be switched off there; authenticated/unauthorised wording counts as auth in both lenses. v0.6.20 · #682 #670 · https://github.com/olafkfreund/PFactory/releases/tag/v0.6.20
- Plan-session routes reject unknown body fields with 422 (a behaviour change). v0.6.20 · #671 · https://github.com/olafkfreund/PFactory/releases/tag/v0.6.20
- Code-aware planning reads C#, Kotlin, PHP, Swift and C/C++ paths; acceptance criteria that wrap across lines keep their continuation. v0.6.19 · #510 · https://github.com/olafkfreund/PFactory/releases/tag/v0.6.19
- Language detection resolves by signal strength; the TFactory block reports `language_source: detected | default`. v0.6.26, v0.6.30 · #801 #827 #824 #892 · https://github.com/olafkfreund/PFactory/releases/tag/v0.6.30
- Cost routing honours a contract's pinned model and declared class, and skips unavailable models. v0.6.30 · #830 #893 #826 #890 · https://github.com/olafkfreund/PFactory/releases/tag/v0.6.30
- Emit attaches the registry's matching skills to the contract. v0.6.20 · #687 · https://github.com/olafkfreund/PFactory/releases/tag/v0.6.20

### 5. Governance and audit evidence
- The run signature (`<slug>.run.json`, `signature_schema: 2`) records risk class, autonomy tier and verdict, data classification, approver, and the control domains the run's gates engaged. Unknown values are `"unknown"` or `null`, never a default. `change_id`, `originator`, `agent_identity` and `model_route` stayed `null` at this release. v0.6.27 · Factory#1961 · https://github.com/olafkfreund/PFactory/releases/tag/v0.6.27
- `python -m plan.governance_cli` answers which plans engaged a control, at what tier, approved by whom, and always prints how many rows it scanned. v0.6.27 · https://github.com/olafkfreund/PFactory/releases/tag/v0.6.27
- Concurrent audit writes no longer fork the hash chain (advisory lock plus a `chain_seq` column; old chains still verify), and background audit rows join the chain. v0.6.23 · #806 · https://github.com/olafkfreund/PFactory/releases/tag/v0.6.23
- A completion event can claim `emitted` only with evidence (an epic issue, or a started build on the trusted-plan path); otherwise it is reported `failed`. v0.6.18 · #141 #143 · https://github.com/olafkfreund/PFactory/releases/tag/v0.6.18
- Optional Ed25519 signature on the emitted contract next to the HMAC one, warn-only; no key is configured, so nothing changes yet. v0.6.35 · #929 · https://github.com/olafkfreund/PFactory/releases/tag/v0.6.35
- The control catalog and extension registry are drift-checked against the hub in CI, because the registry decides which lenses and runtimes run. v0.6.27, v0.6.28 · Factory#1709 · https://github.com/olafkfreund/PFactory/releases/tag/v0.6.28

### 6. Hand-off to the rest of the Factory line
- The handback sender to AIFactory now sends a valid triage block (`handback-triage-1`) with bearer auth; sending stays **off by default** (`PFACTORY_HANDBACK_SEND`). v0.6.35 · #928 #930 · https://github.com/olafkfreund/PFactory/releases/tag/v0.6.35
- The completion webhook to CFactory authenticates with a bearer token; CFactory accepts events with or without it until its own enforce step. v0.6.35 · #931 · https://github.com/olafkfreund/PFactory/releases/tag/v0.6.35
- Correlation keys are scoped to the repo, so issue 12 in two repos no longer lands on one CFactory work item. v0.6.29, v0.6.40 · #878 #965 · https://github.com/olafkfreund/PFactory/releases/tag/v0.6.40
- Agent CLI versions baked into the image were bumped three times (latest in release: claude-code 2.1.310, gemini-cli 0.65.0, codex 0.164.0). v0.6.26, v0.6.29, v0.6.35 · #789 #845 #927 · https://github.com/olafkfreund/PFactory/releases/tag/v0.6.35

### 7. Runtime invariants and delivery pipeline
- Runtime invariants are on by default: every package under `apps/backend` and `apps/web-server` declares checks in `_invariants.py`; non-critical checks run on a timer (default 300 s), violations log and increment `factory_invariant_violations_total`, `GET /api/ready` runs the critical checks. No check is critical yet, so `/api/ready` returns 200 and the readiness probe is unchanged. `FACTORY_INVARIANTS=0` turns it off. v0.6.28 · #864 #865 · https://github.com/olafkfreund/PFactory/releases/tag/v0.6.28
- A migration that shadowed the backend `services` package kept the services invariant companion from loading at startup; fixed. v0.6.33 · #911 #917 · https://github.com/olafkfreund/PFactory/releases/tag/v0.6.33
- Green Dependabot base-image digest bumps merge themselves (only Docker-only PRs; required checks still decide). v0.6.19 · #735 · https://github.com/olafkfreund/PFactory/releases/tag/v0.6.19
- Runner images are published, signed and used; all six test lanes now run on TFactory's runner images. v0.6.19, v0.6.28 · #493, Factory#1003 · https://github.com/olafkfreund/PFactory/releases/tag/v0.6.28
- Rebrand from "Magestic AI" to PFactory in user-facing strings. v0.6.17 · #134 · https://github.com/olafkfreund/PFactory/releases/tag/v0.6.17

## In progress (dev only, merged to `dev`, not in any release)
`gh api repos/olafkfreund/PFactory/compare/main...dev`: 9 commits ahead, 1 behind. None of these is shipped.
- Scoped `acw_` keys accepted on WebSockets (`/ws/events` and the agent-console socket). [#991](https://github.com/olafkfreund/PFactory/pull/991), merged 2026-11-14.
- `/ws/events` confined to the orgs the caller may read; before this every event went to every socket. JWT sockets stay unfiltered until `RBAC_ENFORCE_TASK_ROUTES` is on. [#994](https://github.com/olafkfreund/PFactory/pull/994), merged 2026-11-15.
- Agent child processes get an allowlisted environment, so they cannot read the control plane's tokens, database URL or S3 keys. [#997](https://github.com/olafkfreund/PFactory/pull/997), merged 2026-11-14.
- Plan sessions record originator and agent identity at intake, and the run signature emits them (they were always null). [#1000](https://github.com/olafkfreund/PFactory/pull/1000), merged 2026-11-15.
- RFC-0021 Phase 1: exact-repeat gate on memory writers (`record_gotcha`, `save_session_insights`). [#992](https://github.com/olafkfreund/PFactory/pull/992), merged 2026-11-14.
- Helm hook Job runs `alembic upgrade head` when `migrations.autoApply=false` (the chart default had promised one but no template existed). [#987](https://github.com/olafkfreund/PFactory/pull/987), merged 2026-10-31 after the v0.6.42 tag.
- `libexpat1>=2.10.0-r0` floor for HIGH CVEs; its PR body says it was not verified locally and relied on CI. [#993](https://github.com/olafkfreund/PFactory/pull/993).
- Dependency bumps: agent CLI pins (claude-code 2.1.319, gemini-cli 0.67.0, codex 0.167.0) [#989](https://github.com/olafkfreund/PFactory/pull/989); GitHub Actions group [#995](https://github.com/olafkfreund/PFactory/pull/995).

## Candidate homepage headline features
1. **Review lenses plus a hard readiness gate before any code is written**: 7 lenses (6 always on, Red Team on by default in the registry), a plan whose example contradicts its own invariant is blocked, and per-lens verdicts name what blocked it. Evidence: `base.py:71-89`, `extension-registry.json:32-47`, v0.6.19 #402, v0.6.28. Use the lens count of 7; fix the stale "4 lenses" copy.
2. **Signed, auditable plans**: HMAC-signed Task Contract, run signature v2 with risk class, autonomy tier, approver and engaged controls, a hash-chained audit log that no longer forks under concurrency, and a governance query CLI. Evidence: v0.6.27, v0.6.23, v0.6.35 (Ed25519 optional, no key configured yet).
3. **Hardened for shared deployment**: runs as several replicas on shared Postgres, org-scoped access for API keys, role checks in shadow mode with a written enforce runbook, OIDC token validation, fail-closed defaults. Evidence: v0.6.20 to v0.6.25, v0.6.37 to v0.6.42. Say "shadow mode" for human role checks.
4. **Plans that read your repo**: read-only reconnaissance of the target repo (never executes it), now covering C#, Kotlin, PHP, Swift and C/C++, with code-aware planning and migration detection. Evidence: v0.6.19; extension-registry.json:15-21.
5. **Fits the Factory line**: emits the contract that AIFactory builds and TFactory verifies, authenticated completion events to CFactory, repo-scoped correlation keys. Evidence: v0.6.35, v0.6.40. Handback sending is off by default; do not present it as automatic.

## Not claimed / unverified
- Release notes were taken as written; I confirmed tags, dates and the dev-only list with `gh`, not each PR's code.
- No numbers for users, uptime, performance or adoption were found; none are given.
- "Pipeline stage count" has no single source of truth in code (see above).
