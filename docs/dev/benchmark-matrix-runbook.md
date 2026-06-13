---
title: Benchmark matrix on the live fleet — runbook
updated: 2026-06-13
---

# Running the PARR benchmark matrix on the live fleet

This is the operational runbook for exercising the live Factory fleet with the
`aifactory-demo` benchmark harness: how to run it, how to read the results, the
problems that were found and fixed on 2026-06-13, the known observability gaps,
and exactly how to proceed. If you only read one doc before running a benchmark,
read this one.

Companion docs: [secrets-and-tokens.md](./secrets-and-tokens.md) (credential
refresh), [local-ports-and-run-all.md](./local-ports-and-run-all.md).

---

## TL;DR — current state (2026-06-13)

- The full PARR pipeline (PFactory plan -> AIFactory code -> TFactory verify) is
  **proven end-to-end on the live fleet**. First real green: `api-gateway` on
  Claude — code passed (1,513,998 tokens, $0.84) and verify passed.
- Four real blockers were found and fixed (details below): an **expired Claude
  OAuth token**, a **missing `plan-type:*` GitHub label**, the **Gemini CLI trust
  guard**, and **two harness false-positive bugs**.
- The agent sandbox **cannot** `kubectl port-forward` (no egress). Run the harness
  **inside the AIFactory pod** instead (it has a clone of `aifactory-demo`).
- Known gaps remain in the observability split (per-worker token/cost are `None`;
  `build_report.json` parallelism fields are not wired) — see "Known gaps".

---

## Fleet topology you need to know

All four services run in k8s namespace `factory`, one Deployment each.

| Service | In-cluster URL | Container port | Storage |
|---|---|---|---|
| AIFactory | `http://aifactory.factory.svc.cluster.local:3101` | 3101 | PVC `/home/nonroot/.aifactory` |
| PFactory | `http://pfactory.factory.svc.cluster.local:3114` | 3114 | PVC `/home/nonroot/.pfactory` |
| TFactory | `http://tfactory.factory.svc.cluster.local:3103` | 3103 | PVC `/home/nonroot/.tfactory` |
| CFactory | `http://cfactory.factory.svc.cluster.local:3111` | 3111 | PVC `/home/nonroot/.cfactory` |

Notes:
- Ports **differ from the harness defaults** (`run_benchmark.py` defaults pfactory
  to 3198 and tfactory to 3102 — override via env, see below).
- Each service stores state on a **PVC as SQLite + files**, not a shared DB. The
  SQLite `data.db` holds only auth/org/audit rows; the **tasks live on the
  filesystem**: `workspaces/<project>/.<svc>/specs/<spec-id>/` for AIFactory and
  PFactory, and `workspaces/<project>/specs/<spec-id>/` for TFactory.
- Auth: the shared `APP_API_TOKEN` (key in Secret `factory-secrets`) is a valid
  `Bearer` for AIFactory / PFactory / TFactory. **CFactory's API rejects it**
  (different auth — unresolved; not needed to run the benchmark).

---

## How to run a benchmark (the only way that works today)

Because the agent sandbox has no pod-network egress, `kubectl port-forward` fails
(exit 144). `kubectl exec` / `kubectl cp` work (API-server path), so run the
harness **inside the AIFactory pod**, which already has a clone of the benchmark
repo at `…/.aifactory/workspaces/olafkfreund-aifactory-demo/` (scripts + briefs +
python3 + PyYAML all present).

### 1. (If you edited the harness locally) copy it into the pod

```bash
POD=$(kubectl get pod -n factory -l app=aifactory -o jsonpath='{.items[0].metadata.name}')
kubectl cp scripts/run_benchmark.py \
  "factory/$POD:/home/nonroot/.aifactory/workspaces/olafkfreund-aifactory-demo/scripts/run_benchmark.py" \
  -c aifactory
```

### 2. Launch a scenario (detached, survives the exec session)

```bash
kubectl exec -n factory deploy/aifactory -- sh -c '
cd /home/nonroot/.aifactory/workspaces/olafkfreund-aifactory-demo
export AIFACTORY_API=http://127.0.0.1:3101
export PFACTORY_API=http://pfactory.factory.svc.cluster.local:3114
export TFACTORY_API=http://tfactory.factory.svc.cluster.local:3103
export CFACTORY_API=http://cfactory.factory.svc.cluster.local:3111
export AIFACTORY_TOKEN=$APP_API_TOKEN PFACTORY_TOKEN=$APP_API_TOKEN TFACTORY_TOKEN=$APP_API_TOKEN
# Provider choice (see matrix below). Omit BENCH_MODEL for the factory default (Claude).
export BENCH_MODEL=gemini-2.5-pro
setsid nohup python3 -u scripts/run_benchmark.py --scenario api-gateway \
  > /tmp/bench.log 2>&1 < /dev/null &
echo "pid=$!"
'
```

`--scenario <slug>` runs one; `--all` runs every scenario sequentially;
`--dry-run` prints the REST flow with no calls; `--stage plan|code|verify`
(repeatable) runs a subset.

### 3. Poll progress (no long-held exec)

```bash
# harness alive?
kubectl exec -n factory deploy/aifactory -- sh -c 'kill -0 $(pgrep -f run_benchmark) 2>/dev/null && echo RUN || echo DONE'
# log tail
kubectl exec -n factory deploy/aifactory -- tail -20 /tmp/bench.log
# live token/cost for the running build
kubectl exec -n factory deploy/aifactory -- sh -c 'cat $(ls -dt /home/nonroot/.aifactory/workspaces/olafkfreund-aifactory-demo/.aifactory/specs/*/ | head -1)/token_usage.json'
```

### 4. Read results

Written inside the pod at
`…/olafkfreund-aifactory-demo/benchmarks/results/{<slug>.json, RESULTS.md}`.

```bash
kubectl exec -n factory deploy/aifactory -- cat \
  /home/nonroot/.aifactory/workspaces/olafkfreund-aifactory-demo/benchmarks/results/RESULTS.md
```

A typical build leg is ~20-28 min; verify is ~20-25 min. `BENCH_BUILD_TIMEOUT`
(default 5400s) and `BENCH_VERIFY_TIMEOUT` (default 1800s) cap each.

---

## The provider matrix (Claude vs Gemini)

- **Claude**: omit `BENCH_MODEL`. All phases use `claude-sonnet-4-6` (the default).
- **Gemini**: `BENCH_MODEL=gemini-2.5-pro`. This sets the task `model`, which
  drives the **coding** phase to Gemini, but **planning stays Claude** because
  `phase_config.DEFAULT_PHASE_MODELS` pins every phase to `sonnet` and the
  `model` field does not override it. So a "Gemini run" is really
  *Claude-plans, Gemini-codes* — a legitimate heterogeneous test.
- **Pure Gemini** (planning too): the task must carry
  `metadata.phaseModels = {spec,planning,coding,qa,qa_fixer: "gemini-2.5-pro"}`.
  The harness does not send this yet — see "Known gaps / follow-ups".
- The Gemini path runs `antigravity --yolo` (the gemini->antigravity alias) and
  needs `GEMINI_CLI_TRUST_WORKSPACE=true` on the deployment env (already set).

---

## How to read the result (important — "human_review" is success)

`RESULTS.md` columns: Plan | Code | Verify | Handbacks | Tokens | Cost | Overall.

- A **successful AIFactory build ends at `status: human_review`**, not
  `completed` — because the demo project has auto-PR/auto-merge OFF, so a finished
  build parks awaiting merge approval. `/api/tasks/{id}/status` then returns
  `is_running: false`. This is a PASS, not a hang.
- The harness marks the **code stage passed only if the build consumed tokens**
  (`tokens > 0`). A 0-token "completion" is a failed build (that is how the
  expired-token bug used to show a false green — now fixed).
- **Verify** passes when TFactory reaches a terminal verdict; `verdict: triaged`
  counts as passed.
- `Overall` is `failed` if *any* stage is `error`/`failed`. A transient or
  config plan-stage error will drag a green build+verify to `overall: failed` —
  check the per-stage `…/results/<slug>.json` before concluding the build failed.

---

## Root-cause log — the four problems found on 2026-06-13 (do not re-debug these)

1. **Expired Claude OAuth token (the big one).** `CLAUDE_CODE_OAUTH_TOKEN` had
   lapsed -> `claude` CLI `401` -> planning (Claude-pinned) produced a 0-token
   stub plan -> `AgentService: Invalid or minimal implementation plan detected`
   -> no build. **Fix:** refresh the token (procedure in
   [secrets-and-tokens.md](./secrets-and-tokens.md#refreshing-the-claude--gemini-provider-credentials)).
   This will recur whenever the token expires — it is the first thing to check if
   builds finish in ~30s with 0 tokens.

2. **Missing `plan-type:*` GitHub label.** PFactory's plan `emit` step runs
   `gh issue create` with a `plan-type:<type>` label and **hard-fails (500) if the
   label does not exist** in the target repo. `olafkfreund/aifactory-demo` had the
   `scenario:*`/`lang:*`/`epic` labels but no `plan-type:*`. **Fix:** the 11
   `plan-type:*` labels now exist in the repo (`software-service`, `feature`,
   `software`, `infrastructure`, `infra`, `hosting`, `testing`, `cicd`, `product`,
   `data`, `generic`). Recreate them if the repo's labels are ever reset:
   `gh label create "plan-type:<t>" --repo olafkfreund/aifactory-demo --color 5319e7 --force`.
   *Better long-term fix (not done): make PFactory's emitter create-or-skip
   missing labels instead of 500.*

3. **Gemini CLI trust guard.** The gemini/antigravity CLI refuses to run in an
   "untrusted" workspace and exits before any API call. **Fix:**
   `GEMINI_CLI_TRUST_WORKSPACE=true` added to the AIFactory deployment env in
   `factory-gitops apps/aifactory/manifests/manifests.yaml`.

4. **Two harness false-positives** (`scripts/run_benchmark.py`). (a) The code
   stage marked `passed` whenever `is_running` went false — so a build that died
   in planning showed green in 30s. Now it requires `tokens > 0`. (b) Verify ran
   even when code failed, burning the full 30-min TFactory timeout on nothing.
   Now verify is skipped if the code stage did not pass. **These edits live in the
   pod's clone and in this repo's working copy of `aifactory-demo` — they are not
   yet committed/pushed to the `aifactory-demo` repo (see follow-ups).**

---

## Known gaps / what is still missing (the follow-up list)

- **Per-worker token/cost are `None`.** `token_usage.json`'s `workers` map records
  each worker's `provider`/`model`/`phase` (verified: 4 workers, even
  heterogeneous — 1x haiku + 3x sonnet), but `totalTokens`/`costUsd` per worker
  are not populated; only the scalar aggregate is. The per-worker observability
  feature ships the structure but not the numbers. (Owner: AIFactory
  `agents/token_attribution.py`.)
- **`build_report.json` parallelism not wired.** It reports
  `parallel:false, workers_max:1, total_waves:0` even when the workers map shows 4
  parallel workers. (Owner: AIFactory build-report writer.)
- **Terminal OTel rollup may not fire at `human_review`.** The completion event +
  OTel worker-metrics batch fire on `TaskPhase.COMPLETED`; a build that parks at
  `human_review` (auto-merge off) may never emit them, so OpenObserve fleet
  aggregates can stay empty for benchmark builds. Live per-worker sub-events may
  still flow. **Verify by querying OpenObserve after a run.** (Owner: AIFactory
  `services/completion.py` / `agent_service.py` terminal block.)
- **Harness edits not upstreamed.** The `BENCH_MODEL` override + the two
  false-positive fixes exist only in this working tree and in the pod clone. They
  should be committed/pushed to `olafkfreund/aifactory-demo` so a fresh pod clone
  (or a new `_ensure_project` re-clone) picks them up.
- **Pure-Gemini planning.** To benchmark Gemini end-to-end (planning included) the
  harness needs to send `metadata.phaseModels`. Not implemented.
- **PFactory plan-stage robustness.** Make `emit` tolerant of missing labels (see
  problem 2) so a fresh repo does not 500.
- **CFactory API auth.** Its REST API 401s on `APP_API_TOKEN`; the per-worker
  cockpit endpoints (`/api/tokens/by_worker`) could not be checked. Find the right
  CFactory token/auth.

---

## Backups (before any destructive op)

Before the 2026-06-13 task wipe, the three data dirs were snapshotted to
`Factory/backups/task-wipe-20260613/` (`wipe-backup-{aifactory,pfactory,tfactory}.tgz`,
integrity-verified). To restore one service:

```bash
POD=$(kubectl get pod -n factory -l app=<svc> -o jsonpath='{.items[0].metadata.name}')
kubectl cp backups/task-wipe-20260613/wipe-backup-<svc>.tgz "factory/$POD:/tmp/restore.tgz" -c <svc>
kubectl exec -n factory deploy/<svc> -- sh -c 'cd /home/nonroot && tar xzf /tmp/restore.tgz'
kubectl rollout restart deploy/<svc> -n factory
```

To wipe tasks again (keep projects/auth): remove
`workspaces/*/.<svc>/specs/*` and `…/worktrees/*` (plus `plan-sessions/*` for
PFactory; TFactory uses `workspaces/*/specs/*`), `git -C <ws> worktree prune`, then
restart the deployment. The SQLite `tasks` table is normally empty. The benchmark's
`_ensure_project` re-registers/re-clones projects, so a wipe is low-risk.

---

## How to proceed (next steps, in order)

1. **Finish the provider matrix.** With all four fixes in place, run each scenario
   on Claude (`--all`, no `BENCH_MODEL`) and on Gemini (`--all`,
   `BENCH_MODEL=gemini-2.5-pro`). Scenarios: `api-gateway`, `rust-hello`,
   `go-hello`, `eks-aws`, `ts-tictactoe`, `tf-k8s`. Expect ~20-28 min/build.
2. **Confirm OTLP populates OpenObserve** after a run (resolves the "terminal
   rollup at human_review" question). If empty, fix the completion-event emission
   so `human_review` builds still emit the rollup, or trigger emission on the
   human_review transition.
3. **Upstream the harness edits** to `olafkfreund/aifactory-demo` (`BENCH_MODEL`,
   `tokens>0` pass gate, verify-skip-on-code-fail).
4. **Close the observability gaps** (per-worker tokens/cost; build_report
   parallelism) — these are the point of the per-worker observability feature.
5. **Harden PFactory emit** against missing labels.
6. Publish the matrix results (the benchmark epic is `aifactory-demo#37`).

---

*Keep this current: when a new blocker is found and fixed, add it to the
root-cause log so it is never re-debugged from scratch.*
