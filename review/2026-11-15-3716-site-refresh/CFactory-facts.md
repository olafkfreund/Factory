# CFactory: what shipped, 2026-08-10 to 2026-11-15

Repo: https://github.com/olafkfreund/CFactory. PR links are `/pull/N` on that repo.

## Method and caveats

- Shipped = merged to `main`. The last commit on `main` is #509 (2026-10-30, b24d6f4); nothing reached `main` after that date.
- For dev PRs, shipped was checked two ways: the PR's merge commit is an ancestor of `main` (GitHub compare, status "ahead"), or the `sync/dev-to-main` PR body names the PR (needed for the Oct cherry-picked syncs, whose commits are not ancestors).
- There are no GitHub releases or tags for CFactory in this window. Deploy runs when a sync PR merges to `main` (sync PR bodies say "Merging triggers deploy.yml"; #423 says "Deploy (CD to ArgoCD)").
- There are no version numbers, so quote dates.
- Everything merged 2026-11-14 is on `dev` only (see the last section). The cockpit that is deployed today does not include it.

## What CFactory is today (3 sentences)

CFactory is the cockpit (control tower) over the PFactory, AIFactory and TFactory suite: one web board and an LLM copilot that follow work from a plan through code to test, with an MCP server so coding agents can drive it. It joins events from the three services onto one work item per issue or card, shows stage, usage, anomalies and an audit trail, and lets a human approve, reject or re-run a stage. Over the last three months the work was mostly about telling the truth on the board (stale, stalled, not-run and unknown states), correlating work across the three services, and hardening access and CI gates.

## Themes

### 1. A cockpit that does not overstate

- One null `reason` in a TFactory verification level used to blank the whole Mission Control view with a raw Zod error; it now parses, while a wrong type still fails. [#429](https://github.com/olafkfreund/CFactory/pull/429), shipped by [#430](https://github.com/olafkfreund/CFactory/pull/430)
- A test lane that did not run no longer renders as passed: the badge shows `Browser (0/8 run)` for an errored or pending lane, and STAGE COMPLETE needs at least one executed lane and no failed lane. If TFactory sends no `lane_progress`, display is unchanged. [#432](https://github.com/olafkfreund/CFactory/pull/432), [#437](https://github.com/olafkfreund/CFactory/pull/437), shipped by [#433](https://github.com/olafkfreund/CFactory/pull/433)
- After a websocket drop the cockpit refetches state on reconnect instead of showing pre-drop data under a green "live" pill. [#443](https://github.com/olafkfreund/CFactory/pull/443), shipped by [#444](https://github.com/olafkfreund/CFactory/pull/444)
- A stage is judged stuck from its current status (aged from the last real transition), not the last timeline event; review-parked items count under needs-you. [#455](https://github.com/olafkfreund/CFactory/pull/455), shipped by [#456](https://github.com/olafkfreund/CFactory/pull/456)
- Queued stages are never flagged stuck, and a discarded stage no longer raises a failure anomaly. [#459](https://github.com/olafkfreund/CFactory/pull/459), shipped by [#460](https://github.com/olafkfreund/CFactory/pull/460)
- A blog post, "A cockpit that says unknown", was merged straight to `main`. [#359](https://github.com/olafkfreund/CFactory/pull/359) (2026-08-10, the first day of the window)

### 2. Stalled work stays on the board

- Stalled or stuck work items are kept on the board with their history, plan DAG entry and needs-you count instead of being deleted by the progress poller; they are removed after 24 hours without an update (`CFACTORY_STALLED_PRUNE_HOURS`, default 24). [#483](https://github.com/olafkfreund/CFactory/pull/483), shipped by [#485](https://github.com/olafkfreund/CFactory/pull/485)
- A running stage is never deleted by that sweep, however old; the stall flag is set after an idle deadline instead (default 900 s, `CFACTORY_STALL_DEADLINE_SECONDS`). See the retention section below. [#483](https://github.com/olafkfreund/CFactory/pull/483)
- Limitation recorded in code: if the upstream still lists a pruned dead task, the next poll recreates the row with a fresh clock. [store.py `prune_dead` docstring](https://github.com/olafkfreund/CFactory/blob/main/apps/backend/cfactory/store.py#L633-L673) ([#483](https://github.com/olafkfreund/CFactory/pull/483))

### 3. Cards reach the producers and join up across the three factories

- The card's full body (goal, what to build, acceptance criteria, out of scope) is sent to the planner, coder and verifier, not only the acceptance criteria; the PR measured 1000 to 1982 bytes on one card. [#435](https://github.com/olafkfreund/CFactory/pull/435), shipped by [#436](https://github.com/olafkfreund/CFactory/pull/436)
- The AIFactory dispatch payload carries the issue number so completion usage correlates to the card instead of showing `$0.00` and `instrumented: false`. [#427](https://github.com/olafkfreund/CFactory/pull/427), shipped by [#428](https://github.com/olafkfreund/CFactory/pull/428)
- Card-driven test dispatches send TFactory a `git_url` so it can self-register the project (they previously failed with 404). [#439](https://github.com/olafkfreund/CFactory/pull/439)
- A card dispatched to AIFactory joins on its event key. [#481](https://github.com/olafkfreund/CFactory/pull/481), shipped by [#485](https://github.com/olafkfreund/CFactory/pull/485)
- The correlation key is repo-scoped and CFactory accepts both old and new formats (shipped ahead of the other factories sending the new one); the newest task owns a stage. [#487](https://github.com/olafkfreund/CFactory/pull/487), shipped by [#488](https://github.com/olafkfreund/CFactory/pull/488)
- Legacy bare-number correlation-key fallbacks are removed; old rows stay readable but a bare key is only ever matched exactly. Stated as a behaviour change. [#506](https://github.com/olafkfreund/CFactory/pull/506), shipped by [#507](https://github.com/olafkfreund/CFactory/pull/507)
- Cards join AIFactory's project-scoped `af-<project_id>:<spec_id>` key; with no task id no key is set, and a derived key over 128 characters is not set. [#509](https://github.com/olafkfreund/CFactory/pull/509). Its PR body reports 0 `af-` rows in prod, so no migration.

### 4. Copilot and approval actions that do what they say

- The cockpit's reject review now sends a valid AIFactory `apply-correction` body. [#499](https://github.com/olafkfreund/CFactory/pull/499), shipped by [#503](https://github.com/olafkfreund/CFactory/pull/503)
- Propose answers 409 with a reason when there is nothing to act on; the Copilot panel's Propose buttons use real action kinds (they had sent non-existent kinds and silently got a 400). [#469](https://github.com/olafkfreund/CFactory/pull/469), shipped by [#470](https://github.com/olafkfreund/CFactory/pull/470)
- The MCP endpoint accepts JSON-RPC notifications (`notifications/initialized` returns 202), which fixes an MCP handshake that failed for Claude Code. [#440](https://github.com/olafkfreund/CFactory/pull/440), shipped by [#441](https://github.com/olafkfreund/CFactory/pull/441)
- `GET /api/audit` supports `after_id` and `limit` paging; additive. [#491](https://github.com/olafkfreund/CFactory/pull/491), shipped by [#493](https://github.com/olafkfreund/CFactory/pull/493)
- Docs and spec/plan for the Approve action being safe to repeat (the fix itself is in AIFactory, per the sync PR text). [#463](https://github.com/olafkfreund/CFactory/pull/463), [#465](https://github.com/olafkfreund/CFactory/pull/465), shipped by [#464](https://github.com/olafkfreund/CFactory/pull/464), [#466](https://github.com/olafkfreund/CFactory/pull/466)

### 5. Access control (Factory#312), staged and mostly not enforcing yet

- With no `CFACTORY_API_KEYS`, `/api/*` and `/connect/*` now return 401 unless `CFACTORY_API_DEV_OPEN=true` (default off). The sync PR says the live deployment sets keys, so this was a no-op in prod. [#500](https://github.com/olafkfreund/CFactory/pull/500), shipped by [#503](https://github.com/olafkfreund/CFactory/pull/503)
- `/api/events*` checks for a write-scoped key in warn mode by default (`CFACTORY_EVENTS_AUTH_MODE`: `warn` accepts, logs and counts; `enforce` rejects). Warn only; the live deployment runs in warn. The dev-open flags now open only on a case-insensitive `true`. [#502](https://github.com/olafkfreund/CFactory/pull/502), shipped by [#503](https://github.com/olafkfreund/CFactory/pull/503)
- Use of the legacy shared MCP secret is counted and logged as a warning (`CFACTORY_MCP_LEGACY_SECRET_MODE`, default `allow`, so behaviour is unchanged). Visibility only, not enforcement. [#504](https://github.com/olafkfreund/CFactory/pull/504), shipped by [#505](https://github.com/olafkfreund/CFactory/pull/505)
- API keys are checked for entropy where `CFACTORY_API_KEYS` is parsed. [#401](https://github.com/olafkfreund/CFactory/pull/401)
- A git connection's `base_url` is SSRF-guarded before a credential is sent to it. [#413](https://github.com/olafkfreund/CFactory/pull/413), [#417](https://github.com/olafkfreund/CFactory/pull/417), [#418](https://github.com/olafkfreund/CFactory/pull/418)
- The OIDC subject is carried into the audit record for the credential read a human triggers; the PR says it closes the issue only partly. [#425](https://github.com/olafkfreund/CFactory/pull/425)
- Per-factory scoped tokens are NOT shipped; see dev-only below.

### 6. CI and supply-chain gates

- Secret scanning with gitleaks (PR diff, nightly and full history) and a fix so the config and allowlist are actually read. [#384](https://github.com/olafkfreund/CFactory/pull/384), [#394](https://github.com/olafkfreund/CFactory/pull/394), [#398](https://github.com/olafkfreund/CFactory/pull/398)
- A whole-repo blocking security-sink gate, and Gate 5 (banned constructs) wired in as blocking with 0 findings. [#371](https://github.com/olafkfreund/CFactory/pull/371), [#392](https://github.com/olafkfreund/CFactory/pull/392)
- CodeQL widened to the security-and-quality suite, the `actions` language added, and a weekly CodeQL ratchet with a zero baseline (critical, high, error, medium all 0). [#368](https://github.com/olafkfreund/CFactory/pull/368), [#374](https://github.com/olafkfreund/CFactory/pull/374), [#494](https://github.com/olafkfreund/CFactory/pull/494), shipped by [#497](https://github.com/olafkfreund/CFactory/pull/497)
- GitHub Actions pinned to commit SHAs, Trivy no longer runs a fetched `install.sh`, and cosign pinned back to v3.7.0 because newer signatures would be rejected at cluster admission. [#377](https://github.com/olafkfreund/CFactory/pull/377), [#390](https://github.com/olafkfreund/CFactory/pull/390), [#404](https://github.com/olafkfreund/CFactory/pull/404), [#395](https://github.com/olafkfreund/CFactory/pull/395)
- Every job has `timeout-minutes`; a test file outside CI's collected paths fails the build; a workflow-duplication check was added. [#419](https://github.com/olafkfreund/CFactory/pull/419), [#420](https://github.com/olafkfreund/CFactory/pull/420), [#421](https://github.com/olafkfreund/CFactory/pull/421)
- An API contract drift gate replays the backend's real responses through the frontend's zod schemas and diffs a golden file; the sync PR calls it CI-only. [#445](https://github.com/olafkfreund/CFactory/pull/445), shipped by [#446](https://github.com/olafkfreund/CFactory/pull/446)
- factory-github drift check now runs on every PR. [#482](https://github.com/olafkfreund/CFactory/pull/482), shipped by [#485](https://github.com/olafkfreund/CFactory/pull/485)
- The ratchet lint gates renamed files and measures them against where they moved from (main directly, then brought to dev). [#363](https://github.com/olafkfreund/CFactory/pull/363), [#364](https://github.com/olafkfreund/CFactory/pull/364), [#366](https://github.com/olafkfreund/CFactory/pull/366)
- The 2026-08-21 sync carried the 50 commits of the August CI and security work to `main` in one merge, via a resolved merge branch. [#423](https://github.com/olafkfreund/CFactory/pull/423)

### 7. Security hygiene and dependencies

- Closed CodeQL log-injection and stack-trace-exposure alerts, empty-except alerts and dead-code alerts. [#372](https://github.com/olafkfreund/CFactory/pull/372), [#378](https://github.com/olafkfreund/CFactory/pull/378), [#380](https://github.com/olafkfreund/CFactory/pull/380), [#409](https://github.com/olafkfreund/CFactory/pull/409)
- Error responses stop naming internal endpoints (httpx failures) or returning raw exception text, and `error_reference` keeps its traceback without leaking it. [#383](https://github.com/olafkfreund/CFactory/pull/383), [#391](https://github.com/olafkfreund/CFactory/pull/391), [#402](https://github.com/olafkfreund/CFactory/pull/402)
- Re-vendored shared code from the hub; one change closes a WIQL injection in the vendored factory-github. [#385](https://github.com/olafkfreund/CFactory/pull/385), [#387](https://github.com/olafkfreund/CFactory/pull/387), [#415](https://github.com/olafkfreund/CFactory/pull/415), [#474](https://github.com/olafkfreund/CFactory/pull/474)
- Frontend zod moved from 3 to 4.6.6 for CVE-2023-54404; Debian security updates applied to the backend base image; 65-violation ruff backlog cleared. [#496](https://github.com/olafkfreund/CFactory/pull/496), [#400](https://github.com/olafkfreund/CFactory/pull/400), [#403](https://github.com/olafkfreund/CFactory/pull/403), shipped by [#497](https://github.com/olafkfreund/CFactory/pull/497) (zod)
- Routine Dependabot bumps (Actions groups, vitest, js-yaml, browserslist, lockfile). [#379](https://github.com/olafkfreund/CFactory/pull/379), [#449](https://github.com/olafkfreund/CFactory/pull/449), [#450](https://github.com/olafkfreund/CFactory/pull/450), [#452](https://github.com/olafkfreund/CFactory/pull/452), [#453](https://github.com/olafkfreund/CFactory/pull/453), [#468](https://github.com/olafkfreund/CFactory/pull/468), [#475](https://github.com/olafkfreund/CFactory/pull/475), [#477](https://github.com/olafkfreund/CFactory/pull/477)

## In progress (dev only, NOT shipped)

All merged to `dev` on 2026-11-14; no sync PR to `main` yet (main head is 2026-10-30).

- Model gateway route for the copilot: OpenAI-compatible chat goes to a configured gateway only when `CFACTORY_MODEL_GATEWAY_URL` is set (off by default, no fallback to the provider on gateway error); the provider status probe then hits the gateway health check only. Stage 1 groundwork, "does not close" Factory#1959. [#513](https://github.com/olafkfreund/CFactory/pull/513)
- Per-factory scoped tokens: `CFACTORY_PFACTORY_TOKEN` and `CFACTORY_TFACTORY_TOKEN` next to the AIFactory one, falling back to `CFACTORY_UPSTREAM_TOKEN` when unset; with nothing set, behaviour is unchanged. Step 1 of a four-PR set; the cut-over needs all four deployed. [#510](https://github.com/olafkfreund/CFactory/pull/510)
- Dependency bumps: python 3.15-slim base image, vite 6.4.6, GitHub Actions group. [#511](https://github.com/olafkfreund/CFactory/pull/511), [#512](https://github.com/olafkfreund/CFactory/pull/512), [#508](https://github.com/olafkfreund/CFactory/pull/508)

## Cockpit views on `main`

Source: `apps/frontend-web/src/dashboard.ts` L36-L49 (the `NAV` list) and `apps/frontend-web/src/App.tsx` L264-L280 (view rendering). The cockpit is a single page that switches on a `view` state; there is no URL router. A task can be opened by `/?task=<key>` (comment in `App.tsx` near L62).

| View id | Label | Component |
| --- | --- | --- |
| overview | Mission Control | MissionControl |
| needs | Needs you | NeedsYouView |
| backlog | Backlog | BacklogView |
| planning | Planning board | PlanningBoard |
| pipeline | Pipeline | Board (stage filter via PipelineStrip) |
| running | Active tasks | RunningTasksView |
| tokens | Tokens | TokensView |
| audit | Audit | AuditView |
| services | Services | ServicesView |
| settings | Settings | SettingsView |

Also in the shell (`App.tsx` imports, L5-L28): pipeline strip (Plan, Code, Test), event ticker, command palette, task detail, Copilot panel, theme toggle, portal switcher and toasts.

## How stalled and running work is retained today (`apps/backend/cfactory/store.py` on `main`, b24d6f4)

- Stall flag: a non-terminal stage idle past 900 s (env `CFACTORY_STALL_DEADLINE_SECONDS`) is marked `stalled`. [L36-L52](https://github.com/olafkfreund/CFactory/blob/b24d6f492b6cad21f255826c9859fd9a079258fe/apps/backend/cfactory/store.py#L36-L52), flag computed at L105.
- Dead-row removal age: 24 h (`CFACTORY_STALLED_PRUNE_HOURS`). [L55-L67](https://github.com/olafkfreund/CFactory/blob/b24d6f492b6cad21f255826c9859fd9a079258fe/apps/backend/cfactory/store.py#L55-L67)
- `prune_dead` deletes a work item only when its furthest-along stage is dead (stalled or stuck) and the row has not changed for that age. A running stage is never deleted there, however old; liveness flags it. [L633-L673](https://github.com/olafkfreund/CFactory/blob/b24d6f492b6cad21f255826c9859fd9a079258fe/apps/backend/cfactory/store.py#L633-L673) (delete at L671)
- `reconcile_snapshot` clears a service's stage only when it is non-terminal and not dead, and its task is no longer live upstream; completed, failed and stalled stages are kept. [L607-L631](https://github.com/olafkfreund/CFactory/blob/b24d6f492b6cad21f255826c9859fd9a079258fe/apps/backend/cfactory/store.py#L607-L631)
- Running progress: the per-worker heartbeat series is capped at 120 points (about 20 minutes at a 10 s heartbeat) and dropped on a terminal event. [L137-L142](https://github.com/olafkfreund/CFactory/blob/b24d6f492b6cad21f255826c9859fd9a079258fe/apps/backend/cfactory/store.py#L137-L142), [L286-L292](https://github.com/olafkfreund/CFactory/blob/b24d6f492b6cad21f255826c9859fd9a079258fe/apps/backend/cfactory/store.py#L286-L292)
- Orphan cleanup: `prune_duplicate_stages` removes a stage reported under a different correlation key, and the row if no stage data remains. [L675-L700](https://github.com/olafkfreund/CFactory/blob/b24d6f492b6cad21f255826c9859fd9a079258fe/apps/backend/cfactory/store.py#L675-L700)

## Candidate homepage headline features (all shipped to `main`)

1. A board that says "unknown" or "not run" instead of green: not-run test lanes, reconnect refetch, schema failures no longer blank the view. Evidence: #429/#430, #432/#433, #437, #443/#444, blog #359.
2. Stalled work stays visible for 24 hours with its history, and counts in "Needs you". Evidence: #483/#485, #455/#456, #459/#460. Say "24 h by default, configurable".
3. A card carries its full brief through plan, code and test, and the three services' events join to one item. Evidence: #435/#436, #439, #427/#428, #481, #487/#488, #509.
4. Staged access hardening: `/api` and `/connect` fail closed without keys, events auth and legacy-secret use are warn/count only for now, SSRF guard on git connections. Evidence: #500, #502, #504, #413. Do not claim enforcement of events or MCP auth.
5. CI gates for the cockpit repo itself: secret scanning, blocking security-sink and banned-construct gates, weekly CodeQL ratchet, API contract drift gate. Evidence: #384, #371, #392, #494, #445/#446.

Not safe for the homepage as shipped: per-factory scoped tokens (#510) and model gateway copilot route (#513) are dev only.

## Roadmap-facing notes

- Next on `dev`: gateway-routed copilot (flag, off by default), per-factory cockpit tokens (needs a four-PR cut-over), then the `enforce` mode for events auth and refusing the legacy MCP secret, which both exist but default to non-enforcing (the PRs describe these as slices of Factory#312; no date is stated).
- Open PRs against CFactory at time of writing: none.
