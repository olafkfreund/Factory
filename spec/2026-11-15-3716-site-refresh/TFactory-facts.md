# TFactory: what shipped, 2026-08-10 to 2026-11-15

Sources: GitHub release notes for v0.9.26..v0.9.49 (saved in TFactory-releases.md), `gh api` on olafkfreund/TFactory (releases, tree of `main`, compare `main...dev`, file contents on `main`). Fetched 2026-11-15. All read-only.
Release tag URL pattern: https://github.com/olafkfreund/TFactory/releases/tag/<tag>
PR/issue pattern: https://github.com/olafkfreund/TFactory/pull/<n> (a bare `#n` is a TFactory PR/issue; `Factory#n`, `AIFactory#n`, `CFactory#n`, `PFactory#n` are in the sibling repos and are not linked here).

## Window facts you must not get wrong

- Current version: **v0.9.49, released 2026-10-31** (latest, `isLatest`). Nothing has been tagged since; today is 2026-11-15.
- **No release was tagged between 2026-07-22 (v0.9.25) and 2026-09-18 (v0.9.26).** So the first two thirds of the window (08-10 to 09-18) has no tagged release. v0.9.26 is a large catch-up note: it includes fixes (e.g. #995, #1014, #1018, #1104) that landed before 09-18 and were first released then. Date them "first released in v0.9.26 (2026-09-18)", not as August work.
- 24 tags in the window: v0.9.26 (09-18), v0.9.27 (09-18), v0.9.28 (09-26), v0.9.29 (10-08), v0.9.30 (10-15), v0.9.31 (10-17), v0.9.32 to v0.9.37 (10-22 to 10-23), v0.9.38 (10-23), v0.9.39 to v0.9.41 (10-24), v0.9.42 to v0.9.44 (10-26), v0.9.45 (10-27), v0.9.46, v0.9.47 (10-30), v0.9.48, v0.9.49 (10-31).
- 355 PRs merged in the window, all branches, dependency bumps included (`gh search prs --repo olafkfreund/TFactory --merged --merged-at 2026-08-10..2026-11-15`). This includes the 8 unreleased dev PRs below; a "shipped PRs" number would need the release list, so not claimed.

## What TFactory is today (3 sentences)

TFactory takes a finished feature's acceptance criteria (from AIFactory, Claude Code or a plain file, via MCP or REST) and generates tests across five lanes (unit, browser, api, integration, mutation). It runs them in isolated per-task sandboxes (ephemeral Kubernetes Jobs with a Nix toolchain), grades each test with a mutation-, stability- and coverage-based verdict, and reports which acceptance criteria were actually verified. Results go back to the originating tools as a triage report, PR comment and hand-back, while access control and supply-chain checks have been tightened release by release. (Basis: README on `main`, plus the releases below.)

## Themes (shipped, in release tags)

### 1. Verdicts that say only what was measured

- Coverage from the unit lane now reaches the verdict; verdicts match plan subtasks by id, then test file, so a paraphrased id no longer leaves a fabricated judge `0`. [v0.9.26](https://github.com/olafkfreund/TFactory/releases/tag/v0.9.26) · [#1296](https://github.com/olafkfreund/TFactory/pull/1296), [#1258](https://github.com/olafkfreund/TFactory/issues/1258)
- Handback and triage text labels each reason as **Measured** or **LLM-authored, not verified**, so a QA fixer can tell them apart. Additive JSON change. v0.9.26 · [#1298](https://github.com/olafkfreund/TFactory/pull/1298), [#1195](https://github.com/olafkfreund/TFactory/issues/1195)
- A contradictory acceptance criterion is reported `UNVERIFIABLE`, and a generated test whose prose claims it corrected the spec is rejected. v0.9.26 · #896, #995 (issue numbers as cited in the release note)
- Verdict lanes are stamped from the test plan; an unattributed verdict is excluded rather than counted as unit (this had capped every run at VAL-0). v0.9.26 · #1018
- A run that never reached the code under test (command not found, exit 126/127, environment failure) is `not_run`, not a test failure; same for a mutant that never ran and a missing Stryker. [v0.9.29](https://github.com/olafkfreund/TFactory/releases/tag/v0.9.29) [#1348](https://github.com/olafkfreund/TFactory/pull/1348); [v0.9.35](https://github.com/olafkfreund/TFactory/releases/tag/v0.9.35) [#1402](https://github.com/olafkfreund/TFactory/pull/1402); [v0.9.38](https://github.com/olafkfreund/TFactory/releases/tag/v0.9.38) #1415, #1419
- A dead equivalence-lane harness now yields a `reject` naming the dead harness instead of reading empty output as a golden corpus. v0.9.26 · #959
- Batched Nix pytest lanes now keep `junit.xml`/`coverage.xml`, so coverage is measured instead of reading 0. [v0.9.36](https://github.com/olafkfreund/TFactory/releases/tag/v0.9.36) · [#1408](https://github.com/olafkfreund/TFactory/pull/1408)
- Verify runs record which model actually served the tokens (`usage.workers`), never back-filled from the request. v0.9.26 · #869

### 2. More languages run in-cluster

- Kotlin unit tests run in-cluster via Gradle in a per-task Nix Job; a Kotlin-only plan no longer ends as `evaluated_empty`. [v0.9.27](https://github.com/olafkfreund/TFactory/releases/tag/v0.9.27) · [#1310](https://github.com/olafkfreund/TFactory/pull/1310)
- The Planner can emit Kotlin subtasks; its language list now comes from the framework registry. [v0.9.28](https://github.com/olafkfreund/TFactory/releases/tag/v0.9.28) · [#1322](https://github.com/olafkfreund/TFactory/pull/1322)
- Java unit tests run in-cluster through Maven (Gradle-only Java projects run `gradle test`). [v0.9.29](https://github.com/olafkfreund/TFactory/releases/tag/v0.9.29) · [#1333](https://github.com/olafkfreund/TFactory/pull/1333), [#1351](https://github.com/olafkfreund/TFactory/pull/1351)
- JVM tests are graded per class with one stability pass per build root. [v0.9.32](https://github.com/olafkfreund/TFactory/releases/tag/v0.9.32) · [#1383](https://github.com/olafkfreund/TFactory/pull/1383)
- Swift is explicitly refused ("no in-cluster Swift lane") rather than looking supported. v0.9.32 · [#1389](https://github.com/olafkfreund/TFactory/pull/1389)

### 3. Reproducible, isolated verification

- Spec ingest takes an optional `ref` (branch, tag or full 40-char SHA), fetches it and verifies a detached per-run worktree; `source_ref` and `source_sha` are recorded, and the shared checkout is not touched. [v0.9.38](https://github.com/olafkfreund/TFactory/releases/tag/v0.9.38) · [#1404](https://github.com/olafkfreund/TFactory/issues/1404), [#1416](https://github.com/olafkfreund/TFactory/pull/1416)
- A git-tracked `flake.nix` in the repo puts a contract-less run on Nix in the repo's own devShell; untracked/generated flakes never count and are cleaned up. v0.9.38 #1397; [v0.9.35](https://github.com/olafkfreund/TFactory/releases/tag/v0.9.35) [#1403](https://github.com/olafkfreund/TFactory/pull/1403); [v0.9.37](https://github.com/olafkfreund/TFactory/releases/tag/v0.9.37) [#1410](https://github.com/olafkfreund/TFactory/pull/1410)
- Verify always packs its workspace through the object store; the repo PVC co-mount is gone, and a pack failure records `not_run` / `environment`. This is groundwork for running verify on any node (#1160). [v0.9.33](https://github.com/olafkfreund/TFactory/releases/tag/v0.9.33) [#1392](https://github.com/olafkfreund/TFactory/pull/1392), [#1394](https://github.com/olafkfreund/TFactory/pull/1394); [v0.9.34](https://github.com/olafkfreund/TFactory/releases/tag/v0.9.34) [#1398](https://github.com/olafkfreund/TFactory/pull/1398); [v0.9.37](https://github.com/olafkfreund/TFactory/releases/tag/v0.9.37) (#1160 PR B)
- The runtime image takes Node from the official image instead of apk (v26, matching `.nvmrc`). v0.9.26 · #1301

### 4. Hand-offs with AIFactory, CFactory and PFactory

- Every terminal verify status now sends the completion event to CFactory, so early-ending runs no longer stay pending. [v0.9.30](https://github.com/olafkfreund/TFactory/releases/tag/v0.9.30) · [#1372](https://github.com/olafkfreund/TFactory/pull/1372)
- `GET /api/tfactory/tasks/{spec_id}` returns `source_sha`, so AIFactory's merge gate can tell a verdict for an older commit from the PR head. [v0.9.31](https://github.com/olafkfreund/TFactory/releases/tag/v0.9.31) · [#1378](https://github.com/olafkfreund/TFactory/pull/1378)
- Correlation keys are repo-scoped (`<repo>#<n>`, then project-scoped `tf-<project_id>:<spec_id>`). v0.9.31 [#1377](https://github.com/olafkfreund/TFactory/pull/1377); [v0.9.47](https://github.com/olafkfreund/TFactory/releases/tag/v0.9.47) [#1468](https://github.com/olafkfreund/TFactory/pull/1468); [v0.9.48](https://github.com/olafkfreund/TFactory/releases/tag/v0.9.48) [#1477](https://github.com/olafkfreund/TFactory/pull/1477)
- Spec ingest validates the task contract against the vendored schema: warn mode in [v0.9.41](https://github.com/olafkfreund/TFactory/releases/tag/v0.9.41) ([#1433](https://github.com/olafkfreund/TFactory/pull/1433)), **enforce by default** from [v0.9.43](https://github.com/olafkfreund/TFactory/releases/tag/v0.9.43) ([#1442](https://github.com/olafkfreund/TFactory/pull/1442); `TFACTORY_CONTRACT_SCHEMA_MODE=warn` to revert).
- Ingest verifies PFactory's Ed25519 contract signature in **warn mode** by default (`TFACTORY_CONTRACT_SIGNATURE_MODE`, `enforce` available); with no keys configured every contract warns "unsigned" and still ingests. [v0.9.44](https://github.com/olafkfreund/TFactory/releases/tag/v0.9.44) · [#1444](https://github.com/olafkfreund/TFactory/pull/1444)
- Every handback path sends triage, manifest hash and correlation key. [v0.9.42](https://github.com/olafkfreund/TFactory/releases/tag/v0.9.42) · [#1436](https://github.com/olafkfreund/TFactory/pull/1436)
- Handback to AIFactory and completion events to CFactory carry a bearer token (handback sending itself stays off by default, `TFACTORY_HANDBACK_SEND`). v0.9.44 · [#1446](https://github.com/olafkfreund/TFactory/pull/1446), [#1448](https://github.com/olafkfreund/TFactory/pull/1448)

### 5. Access control and API hardening (mostly shadow mode)

- 20 task-keyed write routes require `member` in the project's org, in **shadow mode** behind `RBAC_ENFORCE_TASK_ROUTES` (default off: would-be denials are logged and audited, not blocked). The notes say not to enable it before RBAC slice S6 because projects have no `org_id` yet. [v0.9.46](https://github.com/olafkfreund/TFactory/releases/tag/v0.9.46) · [#1457](https://github.com/olafkfreund/TFactory/pull/1457); gaps closed in [v0.9.47](https://github.com/olafkfreund/TFactory/releases/tag/v0.9.47) [#1465](https://github.com/olafkfreund/TFactory/pull/1465); worktree reads added in [v0.9.49](https://github.com/olafkfreund/TFactory/releases/tag/v0.9.49) [#1484](https://github.com/olafkfreund/TFactory/pull/1484)
- `GET /api/audit/export` needs org admin/owner (or a service principal). [v0.9.45](https://github.com/olafkfreund/TFactory/releases/tag/v0.9.45) · [#1452](https://github.com/olafkfreund/TFactory/pull/1452)
- API-key scopes are capped by the owner's current org role. v0.9.46 · [#1457](https://github.com/olafkfreund/TFactory/pull/1457)
- Remote MCP authorizes the calling key per tool call (always enforced); remote MCP stays off by default (`TFACTORY_MCP_REMOTE_ENABLED`). Cross-org MCP/REST reads get `403` always. [v0.9.47](https://github.com/olafkfreund/TFactory/releases/tag/v0.9.47) · [#1470](https://github.com/olafkfreund/TFactory/pull/1470), [#1472](https://github.com/olafkfreund/TFactory/pull/1472)
- OIDC ID-token claims (`iss`, `aud`, `exp`, signature algorithm) are enforced. v0.9.47 · [#1464](https://github.com/olafkfreund/TFactory/pull/1464)
- The Copilot MCP endpoint fails closed with `503` when its token is unset. [v0.9.49](https://github.com/olafkfreund/TFactory/releases/tag/v0.9.49) · [#1485](https://github.com/olafkfreund/TFactory/pull/1485)
- Several routes now need `project_id:spec_id` instead of a bare spec id (worktree diff/status/merge-preview/resolve). Behaviour changes in v0.9.47 [#1472](https://github.com/olafkfreund/TFactory/pull/1472), v0.9.48 [#1478](https://github.com/olafkfreund/TFactory/pull/1478), v0.9.49 [#1484](https://github.com/olafkfreund/TFactory/pull/1484).

### 6. Supply chain and code scanning

- All eleven runner images (the sandbox that runs generated code) are signed keyless with cosign and self-verified; publish is a push-only job and PR builds no longer get `id-token: write`. v0.9.26 · Factory#524, #948
- A weekly CodeQL ratchet fails when open critical/high/error/medium alerts exceed a baseline of 0. [v0.9.41](https://github.com/olafkfreund/TFactory/releases/tag/v0.9.41) · [#1426](https://github.com/olafkfreund/TFactory/pull/1426)
- Injection fixes: open-in-IDE/terminal no longer accepts a custom program; project browse/scan is confined to `$HOME` and `APP_FILE_BROWSE_ROOTS`; worktree names and diff `base` refs are validated. [v0.9.40](https://github.com/olafkfreund/TFactory/releases/tag/v0.9.40) [#1424](https://github.com/olafkfreund/TFactory/pull/1424); v0.9.41 [#1429](https://github.com/olafkfreund/TFactory/pull/1429)
- The deploy dry-run (VAL-2) uses `kubectl create --dry-run=server`, so its service account needs no read access to secrets; two filename/flag bypasses in `assert_dry_run` were closed. v0.9.26 · Factory#569
- CVE-gate fixes (each failed the Trivy P0 gate): undici + brotli [v0.9.39](https://github.com/olafkfreund/TFactory/releases/tag/v0.9.39) [#1422](https://github.com/olafkfreund/TFactory/pull/1422); Authlib (CRITICAL) + py3-pip-wheel [v0.9.46](https://github.com/olafkfreund/TFactory/releases/tag/v0.9.46) [#1459](https://github.com/olafkfreund/TFactory/pull/1459), [#1463](https://github.com/olafkfreund/TFactory/pull/1463); joserfc [v0.9.48](https://github.com/olafkfreund/TFactory/releases/tag/v0.9.48) [#1476](https://github.com/olafkfreund/TFactory/pull/1476); uv [v0.9.49](https://github.com/olafkfreund/TFactory/releases/tag/v0.9.49) [#1486](https://github.com/olafkfreund/TFactory/pull/1486). Notes say the Authlib and joserfc flaws were not reachable in this code.

### 7. Reliability and operations

- A build interrupted by a restart no longer shows `in_progress`; phases left `active` are closed as `failed` (behind `APP_INLINE_ORPHAN_RECONCILE_ENABLED`). [v0.9.30](https://github.com/olafkfreund/TFactory/releases/tag/v0.9.30) · [#1375](https://github.com/olafkfreund/TFactory/pull/1375)
- A Job that exited 0 is no longer marked dead by the reaper (mechanism behind false FAILURE anomalies). v0.9.26 · #1014
- Starting a task with `auto_continue: false` no longer crashes after the agent has spawned (`UnboundLocalError`; also fixed in PFactory and AIFactory). v0.9.26 · #1104
- Model timestamps stored as naive UTC; minting an API key with an expiry no longer returns HTTP 500. [v0.9.27](https://github.com/olafkfreund/TFactory/releases/tag/v0.9.27) · [#1309](https://github.com/olafkfreund/TFactory/pull/1309)
- Postgres pool caps cut to 2+2 per pod (was 5+10) with new `DB_*` env vars. v0.9.47 · [#1471](https://github.com/olafkfreund/TFactory/pull/1471)
- `lane_progress` is derived from plan and run artifacts and recomputed on every portal read (it showed `pending` for lanes that had run). v0.9.26 · [#1297](https://github.com/olafkfreund/TFactory/pull/1297); the pipeline board gives `failed`/`generated_empty` terminal badges, v0.9.30 · [#1371](https://github.com/olafkfreund/TFactory/pull/1371)
- `ruff format` is a required check on `dev` and `main`; Alembic models-vs-migrations drift is gated. [v0.9.28](https://github.com/olafkfreund/TFactory/releases/tag/v0.9.28) · [#1318](https://github.com/olafkfreund/TFactory/pull/1318), Factory#2943

Skipped on purpose: pure dependency/CI-action bumps and baked agent-CLI pin bumps (v0.9.32, .44, .46) that are not CVE gates.

## In progress (dev only, not in any release tag)

`gh api repos/olafkfreund/TFactory/compare/main...dev` on 2026-11-15: dev is 11 commits ahead of main, 0 behind. Excluding two merge commits (main-to-dev catch-ups), merged work is:

- Boot migrations serialised with a Postgres advisory lock (2026-10-31). [#1491](https://github.com/olafkfreund/TFactory/pull/1491), issue #1488
- Helm chart gets an alembic hook Job for `migrations.autoApply=false` (2026-10-31). [#1493](https://github.com/olafkfreund/TFactory/pull/1493)
- Scoped `acw_` API keys accepted on WebSocket (2026-11-14). [#1496](https://github.com/olafkfreund/TFactory/pull/1496)
- Memory writers get an exact-repeat gate, "RFC-0021 Phase 1" (2026-11-14). [#1497](https://github.com/olafkfreund/TFactory/pull/1497)
- Agent child processes get an allowlisted environment (2026-11-14). [#1501](https://github.com/olafkfreund/TFactory/pull/1501)
- `/ws/events` confined to the caller's orgs (2026-11-15). [#1500](https://github.com/olafkfreund/TFactory/pull/1500)
- libexpat1 floored at 2.10.0-r0 to clear HIGH CVEs (2026-11-14). [#1498](https://github.com/olafkfreund/TFactory/pull/1498)
- Dependency bumps (github-actions group #1499; baked agent-CLI pins claude-code 2.1.319, gemini-cli 0.67.0, codex 0.167.0 #1494).

Only the commit titles were read for these; behaviour details (flags, defaults) are unverified and need the PRs before any claim beyond the title.

## Numbers a homepage stat grid could use

| Stat | Value | How obtained / caveat |
|---|---|---|
| Current version | v0.9.49 (2026-10-31) | `gh release list`, `isLatest` |
| Releases in window | 24 (v0.9.26 to v0.9.49) | `gh release list`; 13 of them between 10-22 and 10-31 |
| Test files on `main` | **503** (470 Python, 33 TS/JS) | `gh api repos/olafkfreund/TFactory/git/trees/main?recursive=1` (not truncated, 2491 blobs); regex on `test_*.py`, `*_test.py`, `*.test|spec.(ts,tsx,js,jsx)`. This counts files, not test cases; no test-case count was proven. 422 are under `tests/`. |
| Pipeline lanes | 5 (unit, browser, api, integration, mutation) | `_LANE_KEYS` in `apps/backend/tools/runners/lang_registry.py` on `main` |
| Languages with a runnable lane | **4: Python, TypeScript, Java, Kotlin** | Static rows in `lang_registry.py` have tools for python, typescript, java; kotlin comes from `tools/runners/languages/kotlin.yaml` (descriptor); csharp, go, rust, ruby rows are all `None`; swift is refused. Caveat: the file's own header comment says only Python unit and TypeScript unit/browser are "lit" and most cells are `available_at_mvp=False`; there are also `frameworks/go-test` and cucumber/cypress/karate/selenium descriptors that were not traced. Safest wording: "Python, TypeScript, Java and Kotlin have lanes in the registry". Do not claim Go/Rust as supported. |
| Test frameworks with descriptors | 15 `frameworks/*/descriptor.yaml` (incl. portal-ui, cloud-discover, cloud-prowler) | tree of `main` |
| Verdict signals | **5 or 6, say "five-signal"** | README and `agents/confidence.py` weights: mutation 0.30, stability 0.25, semantic 0.20, coverage 0.15, lint 0.10. But `prompts/evaluator.md` numbers six (coverage delta, 3x stability, mutate probe, flake-lint, CI parity, semantic). The two sources disagree; use "five-signal verdict" as the README does, or avoid the number. |
| Pipeline stages | 5 (Planner, Generators, Executor, Evaluator, Triager) | README "High-level architecture" |
| Number of agents | **Cannot be proven.** | `apps/backend/agents/` holds 76 `.py` modules, but those are modules (gates, runners, helpers), not agents; no registry of agents was found. Do not print a number. |
| Signed runner images | 11 (nix runner, portal-ui runner, 9 framework runners) | v0.9.26 note (Factory#524) |
| Merged PRs in window | 355 | `gh search prs --merged-at`, all branches incl. bots |
| Open CodeQL alert baseline | 0 (critical/high/error/medium) | `.github/codeql-baseline.json` per v0.9.41 note; file not re-read live |
| Licence | MIT | `gh repo view` |

## Candidate homepage headline features (3 to 5)

1. **"Verified X/Y" acceptance criteria with measured evidence.** Verdicts separate measured facts from LLM prose, grade per criterion, and report `UNVERIFIABLE` or `not_run` instead of guessing. Evidence: [v0.9.26](https://github.com/olafkfreund/TFactory/releases/tag/v0.9.26) #1298, #1296; [v0.9.35](https://github.com/olafkfreund/TFactory/releases/tag/v0.9.35) #1402; README (acceptance ledger, five-signal verdict).
2. **Reproducible per-task sandboxes.** Nix toolchain in ephemeral Kubernetes Jobs, verifying a pinned commit in a detached worktree, with the commit recorded in the verdict. Evidence: [v0.9.38](https://github.com/olafkfreund/TFactory/releases/tag/v0.9.38) #1404; [v0.9.33](https://github.com/olafkfreund/TFactory/releases/tag/v0.9.33) to [v0.9.37](https://github.com/olafkfreund/TFactory/releases/tag/v0.9.37).
3. **JVM languages in-cluster: Kotlin and Java.** Gradle and Maven lanes added this period, proven live per the notes (3-test fixtures passing and failing under mutation). Evidence: [v0.9.27](https://github.com/olafkfreund/TFactory/releases/tag/v0.9.27), [v0.9.28](https://github.com/olafkfreund/TFactory/releases/tag/v0.9.28), [v0.9.29](https://github.com/olafkfreund/TFactory/releases/tag/v0.9.29).
4. **Works with the rest of the factory.** Signed-contract and schema-checked ingest (schema enforce by default, signature warn-only), `source_sha` for merge gates, project-scoped correlation keys, completion events for every terminal status. Evidence: [v0.9.43](https://github.com/olafkfreund/TFactory/releases/tag/v0.9.43), [v0.9.44](https://github.com/olafkfreund/TFactory/releases/tag/v0.9.44), [v0.9.31](https://github.com/olafkfreund/TFactory/releases/tag/v0.9.31), [v0.9.30](https://github.com/olafkfreund/TFactory/releases/tag/v0.9.30).
5. **Security posture for multi-tenant use.** Signed runner images, weekly CodeQL ratchet at 0, role checks on task routes (shadow mode until enforced), per-call MCP authorization, OIDC claim checks. Say "role checks in shadow mode", not "RBAC enforced". Evidence: [v0.9.26](https://github.com/olafkfreund/TFactory/releases/tag/v0.9.26), [v0.9.41](https://github.com/olafkfreund/TFactory/releases/tag/v0.9.41), [v0.9.46](https://github.com/olafkfreund/TFactory/releases/tag/v0.9.46), [v0.9.47](https://github.com/olafkfreund/TFactory/releases/tag/v0.9.47).

## Cautions for the writer

- The README on `main` still says "Where we are (July 2026, v0.9.x)", so it is stale text, not a source for this window.
- Several items are behind a flag or default-off: RBAC task routes (`RBAC_ENFORCE_TASK_ROUTES`), remote MCP (`TFACTORY_MCP_REMOTE_ENABLED`), handback sending (`TFACTORY_HANDBACK_SEND`), contract signature (warn), `TFACTORY_PACK_WORKSPACE` (ignored since v0.9.37, packing is now always on).
- Release notes cite issue numbers in sibling repos (`Factory#`, `AIFactory#`, `CFactory#`); those are not linked above because only the TFactory repo was read.
- Notes without a PR link for v0.9.26 items cite issue numbers only; I did not resolve them to PRs.
