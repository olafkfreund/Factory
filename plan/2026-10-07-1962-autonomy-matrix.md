---
status: approved
issue: 1962
spec: spec/2026-10-07-1962-autonomy-matrix.md
---

# Plan: publish the autonomy matrix and control mapping, generated from code

## Approved decisions (carried from intent + spec)

- **Generate, never transcribe.** Every row comes from *calling*
  `merge_policy` or `pr_endgame` functions, or from *reading* modules with
  `ast`. The only hand-maintained input is PR 2's `control-objectives.yaml`,
  plus one marked list of cross-repo gate citations.
- **Three generated sections, plus a fourth in PR 2:**
  - **A, policy:** `decide_merge` over a cross-product of its inputs, the
    overlay probes, the VAL semantics and the path floor.
  - **B, live wiring:**
    - blank tier → `low` in `merge_disposition`;
    - the defaults and env-var names of `AIFACTORY_AUTO_MERGE` and
      `AIFACTORY_PATH_RISK_FLOOR_ENFORCE`;
    - whether the path floor changes the tier with enforcement off and on;
    - the unmeasured-signal defaults from `merge_gate_signals`.
  - **C, gate determinism:** an `ast` import-closure prober.
    - Entry points: `merge.merge_policy`, `server.services.pr_review_service`
      and `server.services.pr_endgame`.
    - Pinned model clients: `anthropic`, `openai`, `claude_agent_sdk`,
      `google.genai`, `ollama`, `core.client`, `core.simple_client` and
      `providers`.
    - An empty or under-minimum closure is an error.
    - PFactory and TFactory gates are shown as "declared, unverified".
  - **D (PR 2):** the control-objective mapping, joined from YAML, with an
    orphan check in both directions.
- **No environment axis and no per-tier VAL table.** Neither exists in the
  code.
- **The gate:** AIFactory `.github/workflows/autonomy-matrix.yml`.
  - **No `paths:` filter**, with the hub `contracts.yml` comment copied.
  - Row-count minimums are asserted before the comparison.
  - It becomes a required context on AIFactory `dev` and `main`, but only after
    the workflow is on `dev`.
- **Publication waits for PR 2.** PR 1's page carries `draft: true`
  front-matter. Docusaurus leaves draft docs out of production builds, so
  nothing goes public half-done.
- **Prerequisite (step 0):** the `enforce_admins` experiment. Its result sets
  only PR 2's branch-protection wording.
- Out of scope: any change to merge behaviour, the #1963 floor work, and
  probing PFactory or TFactory.

## Where

- Repo: `olafkfreund/AIFactory`.
  - Branch `feat/1962-autonomy-matrix`, cut from `origin/dev` @ `df22b943`.
  - PRs target **`dev`**.
  - Line numbers below are at that SHA; re-check them if `dev` has moved.
- Hub: `olafkfreund/Factory`, which holds the protection script (step 9) and
  the control-matrix links (step 13).
- Python: the AIFactory backend venv with web-server requirements installed,
  exactly as in `ci.yml:64-66`. `tests/conftest.py:92` puts `apps/backend` on
  `sys.path`. The generator also adds `apps/web-server`.

## Steps

### Step 0: `enforce_admins` experiment (session model; outward-facing, approved with this plan)

1. Create a private repo `olafkfreund/protection-probe-1962`.
   - Add a workflow `fail.yml` with a job `must-pass` that runs `exit 1` on
     `pull_request`.
   - Push `main`.
2. Protect `main`:
   - required check `must-pass`;
   - `strict: true`;
   - `enforce_admins: false`;
   - no review requirement.

   This matches the AIFactory shape.
3. Open a PR from a branch with one trivial commit, and wait for `must-pass`
   to go red.
4. Attempt the merge as the account AIFactory uses (the same `gh auth`):
   1. `gh pr merge <n> --squash`. This is AIFactory's call: `pr_endgame.py`
      `merge_pr` L712, and `approval.py:141`.
   2. If (1) is refused, try
      `gh api -X PUT repos/olafkfreund/protection-probe-1962/pulls/<n>/merge -f merge_method=squash`.
5. Record the commands, the exit codes and the response bodies verbatim in this
   plan's implementation record.
6. Delete the repo with `gh repo delete --yes`. It needs the `delete_repo`
   scope; if that's missing, ask the owner to delete it.

→ verify by: the record shows both attempts and an outcome. The repo is gone.

Traps:
- If (2) **succeeds**, the PR merges. That's the finding.
- File the follow-up under #943 (`enforce_admins: true` in
  `apply_branch_protection.sh`). Don't change protection here.

### PR 1: generator, gate, prober (AIFactory)

**1. `scripts/gen_autonomy_matrix.py`: skeleton and Section A**
- Module docstring and generated banner, in the hub `scripts/gen_contracts.py`
  shape (`_GENERATED_BANNER`, `main(argv)`, `--check`).
- Imports:
  - put `<repo>/apps/backend` and `<repo>/apps/web-server` on `sys.path`;
  - import `merge.merge_policy as mp`, `review_tier` and
    `server.services.pr_endgame as pe` **at module level**;
  - on `ImportError`, print `FATAL: cannot import <name>: <err>` and exit
    **2**.
- **Section A, tiers:**
  - inputs: `sorted(mp._TIER_ALIASES)`, plus `""` and `"bogus"`;
  - for each, the cross-product of `host_ci_green` ∈ {T,F}, verdict ∈
    {"pass","fail"}, `(achieved_val, val_floor)` ∈ {(2,1),(1,2)} and
    `ci_parity` ∈ {T,F};
  - call `mp.decide_merge(tier, …, deployment=None)`;
  - group by `(tier, result)` and render the conditions under which each
    result occurs. "Always" means all 16 combinations; otherwise list the
    combinations, which for `low`→`auto-merge` is the single all-true row.
- **Section A, overlay:** the product of
  - `risk_class` ∈ {"high","medium","low",""};
  - `production_classification` ∈ {"production","staging","dev",""};
  - `system_gates=["human-approval","security-scan"]` with satisfied ∈
    {[], ["security-scan"], both}.

  Render the reasons from `mp.deployment_block_reasons` verbatim, and
  `decide_merge("low", all-green, deployment=d, satisfied_gates=s)`.
  Deduplicate identical rows.
- **Section A, VAL:** call `mp._val_meets_floor` over the 8 spec probes.
- **Section A, path floor:**
  - `review_tier.HIGH_RISK_PATTERNS` rendered as a list;
  - `mp.floor_from_paths([p])` for one probe path per pattern (the pattern
    string itself as a path segment);
  - plus `["README.md"]` and `[]`.
- **Signature guard:** `inspect.signature(mp.decide_merge).parameters` must
  equal the probed set
  `{tier, host_ci_green, tfactory_verdict, achieved_val, val_floor, ci_parity, deployment, satisfied_gates}`.
  Otherwise exit 3: "decide_merge gained parameter X; extend the probe set".

→ verify by: `python scripts/gen_autonomy_matrix.py --stdout | head -80` shows
the tier, overlay, VAL and path-floor tables. `low` auto-merges only on the
all-true row, and the blank and bogus tiers give `hold-blocking`.

Traps:
- **Probe-set completeness:** use `HIGH_RISK_PATTERNS` from the module. Never
  copy the patterns.
- **The overlay must run *before* the tier.** Render what `decide_merge`
  returns, not what you expect.

**2. Section B, live wiring** (same file)
- **Blank vs low:**
  - in a `tempfile.TemporaryDirectory`, write `task_metadata.json` with all-green
    signals, using the camelCase keys from `pe._SIGNAL_KEYS`:
    `tfactoryVerdict:"pass", achievedVal:2, valFloor:1, ciParity:true, hostCiGreen:true`;
  - call `pe.merge_disposition(d, None)`, `pe.merge_disposition(d, "")` and
    `pe.merge_disposition(d, "low")`;
  - render the results and whether blank == low.
- **Unmeasured defaults:** `pe.merge_gate_signals(empty_tmp_dir)`, rendered as
  a key → value table.
- **Flag defaults:**
  - with the `AIFACTORY_AUTO_MERGE` and `pe.PATH_RISK_FLOOR_ENV` env vars
    removed (save and restore `os.environ`), call
    `pe.is_auto_merge_enabled(None)` and `pe.path_floor_enforced(None)`;
  - then set each to `"1"` and call them again;
  - render the env names and both results.
- **Path floor, advisory vs enforced:**
  - temporarily replace `cli.workspace_commands._get_changed_files_from_git`
    with `lambda *a, **k: [<first high-risk probe path>]`
    (`apply_path_risk_floor` imports it lazily, so patching the module
    attribute works);
  - call `pe.apply_path_risk_floor(tmp, tmp_spec, "probe", "dev", "low")`
    with the enforce env unset, then set to `"1"`;
  - render the `(effective_tier, floor)` from each call;
  - restore the attribute in `finally`.
- Footer line: "Defaults shown; per-project settings and per-deployment env
  override them."

→ verify by: `--stdout` shows:
- blank == low → **True**;
- both flags default **False**;
- the path floor gives `(low, blocking)` when advisory and
  `(blocking, blocking)` when enforced.

Traps:
- **Deviation from the spec's wording**, recorded here: the spec said "a temp
  git repo". Patching the differ is used instead, because the differ isn't the
  policy and a git fixture adds fragility for no coverage. What's derived (the
  floor and the enforcement switch) is unchanged.
- `_record_path_risk_floor` writes under `spec_dir`, so use the temp dir.
- `load_task_contract` on an empty temp spec dir must return no deployment. If
  it raises, the function's `except` already covers it.

**3. Section C, determinism prober** (same file)
- `_closure(module_name) -> set[str]`:
  - BFS over `ast.parse` of each resolved file;
  - collect `Import` and `ImportFrom` nodes **anywhere** in the tree, including
    inside functions;
  - resolve relative imports against the package;
  - resolve a module to a file under `apps/backend` or `apps/web-server`
    (`pkg/__init__.py` or `mod.py`);
  - record unresolvable (third-party) names as leaves without walking them.
- `_label(closure)`:
  - "model-assisted" if any name equals, or starts with `<x>.` for, an `x` in
    the pinned set;
  - otherwise "deterministic".
- **Minimum closure sizes:**
  - measure the real counts once;
  - set each minimum to `floor(0.5 × measured)`;
  - commit them as constants with a comment giving the measured value and
    date.
- If a closure is **below its minimum**, exit 4: "prober resolved N modules
  for X (min M) — refusing to label". It must never emit "deterministic".
- **Declared, unverified rows** — a marked literal list (`# DECLARED, not
  derived — cross-repo`):
  - PFactory `plan/review/gates.py::run_gates`;
  - TFactory `apps/backend/agents/evaluator.py::_run_evaluator_session`.

→ verify by: `--stdout` gives:
- `merge.merge_policy` → deterministic;
- `server.services.pr_review_service` → model-assisted;
- `server.services.pr_endgame` → whatever the walk says.

Record the three measured closure sizes in the implementation record.

Traps:
- If `pr_review_service` comes out **deterministic**, the pinned set is
  missing its client. **Stop and report.** Don't add names until it flips.
- `pr_endgame`'s label is reported as observed. The page states that its
  review verdict is injected and shown as a separate component.

**4. Outputs and `--check`** (same file)
- Render to:
  - `docs/docs/compliance/autonomy-matrix.md`, with front-matter
    `draft: true`, `title: Autonomy matrix (generated)` and the banner
    comment;
  - `docs/static/compliance/autonomy-matrix.json`, with
    `json.dumps(…, indent=2, sort_keys=True) + "\n"`.
- `--stdout` prints the markdown only.
- `--check`:
  1. assert row minimums: tier rows ≥ 8, overlay rows ≥ 12, VAL rows = 8,
     path rows ≥ `len(HIGH_RISK_PATTERNS)` + 2, entry points = 3;
  2. regenerate in memory;
  3. compare byte-for-byte with both committed files;
  4. on a mismatch, print the file and its first differing line, and exit 1;
  5. on a match, print `ok: <counts>`.
- Run the generator and commit both output files.

→ verify by: `python scripts/gen_autonomy_matrix.py --check` prints
`ok: tiers=… overlay=… val=8 paths=… gates=3`.

Traps:
- **Determinism:** no timestamps and no `dict` iteration without sorting.
  Use `sorted()` everywhere, or two runs differ.
- **No `xml.etree`, `pickle` or `subprocess`** in the generator: the
  security-sinks lint.

**5. Tests: `tests/test_gen_autonomy_matrix.py`**
1. The rendered markdown contains `mp.AUTO_MERGE`, `mp.HOLD_ASYNC` and
   `mp.HOLD_BLOCKING`, read from the module.
2. `_label(_closure("merge.merge_policy")) == "deterministic"` and
   `_label(_closure("server.services.pr_review_service")) == "model-assisted"`.
3. A prober run on a tmp package whose entry module imports nothing is below
   the minimum and raises or exits 4.
4. `main(["--check"])` returns non-zero when a committed output is tampered
   with. Run against a tmp copy with the paths injected through a function
   argument, not by editing the repo.
5. The signature guard: monkeypatching `mp.decide_merge` to a function with an
   extra keyword exits 3.

→ verify by:
`apps/backend/.venv/bin/pytest tests/test_gen_autonomy_matrix.py -q` is green,
and so is the full `pytest tests/ -q -m "not slow"`.

Traps:
- Import the script with `importlib` from `scripts/`, the way existing tests
  do. Check `tests/` for a precedent first.
- `ruff format` and `ruff check` must be clean. The AIFactory ratchet is
  blocking.

**6. `.github/workflows/autonomy-matrix.yml`**
- Triggers: `pull_request` (all) and `push` to `dev` and `main`.
  - **No `paths:`.** Copy the hub `contracts.yml` "NO `paths:` FILTER,
    DELIBERATELY (Factory#489)" comment block, adjusted to name this gate.
- One job named exactly
  `autonomy matrix matches the policy (--check, blocking)`.
- Setup: copy `ci.yml`'s venv steps (L60-67).
- Run: `apps/backend/.venv/bin/python scripts/gen_autonomy_matrix.py --check`.
- Pin actions by SHA, the same as `ci.yml`.

→ verify by: the job runs on the PR and passes.

Traps:
- The jscpd clone budget: if copying the setup block trips it, reuse the
  composite action `ci.yml` uses, if there is one. Check first.
- Workflow-duplication lint (`workflow-duplication.yml`).

**7. Mutation checks** (session model; scratch commits, reverted, never pushed)
- **A:** in `merge_policy.py`, change `HOLD_ASYNC = "hold-async"` to
  `"hold-async-v2"`. `--check` must exit 1 and name a changed line.
- **B:** in `deployment_block_reasons`, add a block for
  `production_classification == "staging"`. `--check` must exit 1.
- **D:** in `merge_disposition`, change the blank-tier default `"low"` to
  `"medium"`. `--check` must exit 1.
- **Control:** a comment-only change in an unrelated file. `--check` exits 0
  and prints non-zero counts.

→ verify by: record the four outcomes in the implementation record. Then
confirm with `git diff --stat` that the tree is clean.

**8. PR 1 → AIFactory `dev`**
- Title: `feat(compliance): generated autonomy matrix + staleness gate (Factory#1962 PR 1)`.
- Body:
  - links to the Factory intent, spec and plan;
  - the step 7 outcomes;
  - the measured closure sizes;
  - which steps the coder did;
  - "page is `draft: true` until PR 2".
- All checks green, then merge after owner approval.

**9. Make the gate required** (hub `scripts/apply_branch_protection.sh`)
- Add `autonomy matrix matches the policy (--check, blocking)` to AIFactory's
  `CHECKS` (main) and `CHECKS_DEV`, at the AIFactory case arm (~L214).
- Add a comment citing #1962 and the no-`paths:` reason.
- Hub PR → `main`.
- Then run `scripts/apply_branch_protection.sh --repo AIFactory --apply`, the
  way the script documents (L31).

→ verify by:
- `gh api repos/olafkfreund/AIFactory/branches/dev/protection/required_status_checks -q '.checks[].context'`
  lists it on `dev`, and the same on `main`;
- a fresh AIFactory PR shows the check as **Required**.

Traps:
- **Ordering:** run step 9 only after PR 1 has merged to `dev`. A required
  context that `dev`'s workflows never report wedges every PR.
- `main` reports it only on sync PRs from `dev`. That's acceptable because the
  workflow has no `paths:` filter. Check with `git log` that the sync flow runs
  PR checks; if it pushes directly, add the check to `CHECKS_DEV` only and note
  it here.

### PR 2: mapping, publication, links

**10. `docs/compliance/control-objectives.yaml`**
- One entry per derived control id. The generator assigns stable ids:
  `policy.tier.<bucket>`, `policy.overlay`, `policy.val_floor`,
  `policy.path_floor`, `wiring.blank_tier`, `wiring.auto_merge_flag`,
  `wiring.path_floor_flag`, `gate.<entry>`.
- Each entry has fields `objective`, `evidence` (a repo path or URL),
  `frameworks` (a list of clause references) and an optional `claim`.
- The branch-protection `claim` comes from step 0's outcome, worded exactly as
  the spec prescribes.
- The generator reads the YAML with `yaml.safe_load`; PyYAML is already in the
  venv, so check `requirements.txt`.
- Section D is the joined table.
- `--check` also fails on an orphan in either direction, naming the orphan.

→ verify by: delete one YAML entry and `--check` fails naming it; add a bogus
entry and `--check` fails naming it; restore both.

**11. Publish**
- Flip the generator's front-matter from `draft: true` to no draft key.
- Add `'compliance/autonomy-matrix'` to the Compliance items in
  `docs/sidebars.ts` (L72).
- Regenerate and commit.

→ verify by: the docs build job passes on the PR.

**12. PR 2 → AIFactory `dev`.** It goes live on the next `dev`→`main` sync
(`docs.yml` deploys on push to `main`).

→ verify by: after the sync,
`https://olafkfreund.github.io/AIFactory/compliance/autonomy-matrix` returns
200 and shows Section D.

**13. Hub links** (`docs/compliance/control-matrix.md`)
- Add a link to the published page in the evidence cells of the "Agentic-AI
  governance (#323)" and "Change mgmt & SoD (#316)" rows.
- Links only. No content copied.
- Hub PR → `main`.

→ verify by: the links resolve with 200.

Then close #1962, and comment on #1958 and #1963 with the URL and the step 0
outcome.

## Tests

- `apps/backend/.venv/bin/pytest tests/test_gen_autonomy_matrix.py -q` →
  green.
- `apps/backend/.venv/bin/pytest tests/ -q -m "not slow"` → green.
- `python scripts/gen_autonomy_matrix.py --check` → `ok: …` with non-zero
  counts.
- Mutations A, B and D fail and Control passes (step 7). In PR 2, both orphan
  directions fail (step 10).

## Rollback

- **PR 1 and PR 2:** revert the AIFactory PRs. There are no behaviour
  changes, only a script, docs, a test and a workflow.
- **Step 9:** remove the context from `apply_branch_protection.sh` and re-run
  `--apply`. **Remove the required context before reverting the workflow**,
  or every PR wedges.
- **Step 0:** the scratch repo is deleted at the end of the step. If a merge
  went through there, nothing outside the scratch repo is touched.

## Implementation record

### Step 0: `enforce_admins` experiment (2026-10-07, session model)

- **Repo:** `olafkfreund/protection-probe-1962` (private).
  - Required check `must-pass` runs `exit 1`; `strict: true`;
    `enforce_admins: false`; no reviews.
  - The PR's `must-pass` was red and `mergeStateStatus` was `BLOCKED`.
  - Account `olafkfreund`, a repo admin.
- **Attempt 1:** `gh pr merge 1 --squash` was **refused**, exit 1: "the base
  branch policy prohibits the merge … add the `--admin` flag".
- **Attempt 2:** `gh api -X PUT …/pulls/1/merge -f merge_method=squash`
  **merged**, exit 0: `{"merged":true,"sha":"030dd1fa…"}`.
- **Outcome:** the server doesn't enforce the floor for admins.
  - Every AIFactory GitHub merge path uses `gh pr merge` without `--admin`, so
    today the floor holds by client convention.
  - The scratch repo is deleted.
  - Filed on #943 (issuecomment on 2026-10-07).
- **Effect on PR 2 (step 10):** the branch-protection `claim` is: "enforced by
  branch protection for non-admin merges; the fleet's merge paths do not use
  admin bypass, but GitHub does not prevent it while `enforce_admins` is
  false."

### Steps 1–3 (coder, 2026-10-07)

- **Step 1:** `a8b371d5`. The VAL probes were corrected to the spec's exact 8,
  and the blank tier renders as `(blank)`.
- **Step 2:** `c1b761a6`. All three expectations hold:
  - blank == low;
  - both flags default off;
  - the path floor gives `(low, blocking)` when advisory and
    `(blocking, blocking)` when enforced.
- `AIFACTORY_AUTO_MERGE` has no module constant, so the name is restated with a
  `ponytail:` comment. The flag value still comes from calling
  `is_auto_merge_enabled`, so a rename shows up as output drift.
- **Finding, rendered and not changed:** `merge_gate_signals` gives unmeasured
  signals passing defaults:
  - `host_ci_green=True`
  - `tfactory_verdict='pass'`
  - `ci_parity=True`
  - `achieved_val=0` with `val_floor=None`

  So a `low` task with nothing recorded auto-merges when
  `AIFACTORY_AUTO_MERGE` is on. This is documented as deliberate in
  `merge_gate_signals`. It's out of scope here and relevant to #1963.
- **Step 3 deviation: a spawn edge in the prober.** The step 3 stop-trap fired,
  because `server.services.pr_review_service` labelled *deterministic*. The
  service runs the model-backed reviewer as a subprocess
  (`apps/backend/runners/github/runner.py`, through `create_subprocess_exec`,
  with `PYTHONPATH` = backend + `runners/github`), which an import walk can't
  see. The fix, decided by the planner:
  - a marked `_SPAWN_EDGES` literal (caller → script, plus extra import roots
    that mirror the subprocess `PYTHONPATH`);
  - **verified against the caller's AST** on every run: the path string
    constants and a subprocess-exec call must be present, and the script must
    exist, or the run exits 4;
  - the caller's closure = its import closure ∪ the script's closure.

  No label is hardcoded. Minimum closure sizes use `max(2, floor(0.5 × measured))`,
  because `merge_policy`'s closure is 2.

### Steps 3–7 (2026-10-07)

- **Step 3:** `a03879cc`. Measured closures:
  - `merge_policy` is 2, deterministic;
  - `pr_review_service` is 263 via the spawn edge, model-assisted;
  - `pr_endgame` is 352, model-assisted.

  Minimums are 2, 131 and 176.
- **Step 4:** `23684a89`, plus `cef3ce8d` (a readability follow-up: a computed
  "otherwise" and a legend in A1).
- **Step 5:** `9fee2c42`, 7 tests.
  - Full suite: 5526 passed, 60 skipped, 71 deselected, 2 xpassed.
  - Test 3 checks the closure size directly; exit 4 is covered by test 4.
- **Step 6:** `3de0b374`.
  - `actionlint` is clean.
  - The hub's `check_workflow_duplication.py` reports OK.
  - There is no composite setup action to reuse.
- **Step 7, mutations (session model; reverted, tree clean):**
  - **A, value:** exit 1, `line 20 differs: hold-async-v2 vs hold-async`.
  - **B, shape:** exit 1, `line 36 differs`. The overlay auto-merge row went from
    9 to 6 combos.
  - **D, wiring:** exit 1, `line 103 differs`. Blank went from auto-merge to
    hold-async.
  - **Control:** exit 0,
    `ok: tiers=10 overlay=12 val=8 paths=28 gates=3`.

### Independent review of PR 1 and its fixes (2026-10-07)

A fresh Opus reviewer found nothing that blocks. All five findings were fixed
before the PR (`19dfb5ad` generator, `ef5fd21e` tests).

- **HIGH, a deviation in the prober's scope:** the walk skipped parent package
  `__init__` files. `merge/__init__.py` imports `ai_resolver`, which reaches
  the model clients.
  - Decision: the label stays scoped to the gate module's own import edges, and
    the page says so.
  - A **derived** column, "package `__init__` reaches a model client", reports
    the parent-package reach separately. For `merge_policy` it reads: yes, via
    `merge/__init__.py`.
  - Paths are listed on the page when there are 3 or fewer; otherwise there's a
    count, and the full list goes in JSON `gates[].init_reach`.
- **MEDIUM:** a dynamic import (`importlib.import_module` or `__import__`) in a
  closure makes the label `undetermined (…)`, never `deterministic`. In the
  model-assisted rows it's noted in the same cell.
- **LOW:** the spawn edge now requires the three path parts in one assigning
  statement, a spawn call using that variable, and each `extra_root` matched
  in one statement.
- **Tests:** 7 → 15.
  - The vacuous constant and minimum tests were fixed.
  - Added: the spawn-edge negative cases, relative imports, a dynamic import,
    and the parent-`__init__` case.
- **NIT:** the A2 required-gates line is rendered from the probe variable.
- **After the fixes:**
  - `--check` gives
    `ok: tiers=10 overlay=12 val=8 paths=28 gates=3`;
  - the full suite gives 5535 passed, 60 skipped, 71 deselected, 2 xpassed.

### Step 8: PR 1 opened (2026-10-07)

- **PR:** AIFactory#1651 → `dev`.
- **First CI run:** the new gate `autonomy matrix matches the policy (--check, blocking)`
  passed. The ratchet failed because new files are held to the strict
  baselines (`standards/ruff.toml`, `standards/mypy.ini`): 23 ruff findings and
  6 mypy findings.
- **Fixes:** made without blanket `noqa` or `type: ignore`. Outputs are
  byte-identical, and the 15 tests still pass.
- **Final CI:** 52 pass, 5 skipped, 0 fail.
- **Trap for PR 2:** run both strict configs locally before pushing.

### Steps 8 and 9 (2026-10-08)

- **PR 1 merged:** AIFactory#1651 → `dev` @ `c9361690`. The gate ran on the
  `dev` push and passed.
- **How `main` gets changes:** `main` receives `release/*` PRs, which run
  `pull_request` workflows, so the context is required on both branches.
- **Step 9:** hub Factory#3542 → `main` @ `5c13340c`.
  - The context was added to AIFactory `CHECKS` and `CHECKS_DEV`.
  - `tests/test_branch_protection_intent.py` pins it: `_AUTONOMY` in the
    AIFactory/main expectation and in both AIFactory/dev live fixtures.
  - The dry-run before applying showed this context as the only drift.
- **Applied:** `scripts/apply_branch_protection.sh --apply --repo AIFactory`.
  - Live: `dev` has 12 contexts, `main` has 8, and the autonomy gate is on both.
  - A re-check reports "live branch protection matches the declared intent".
- **Trap seen:** the first `--apply` ran while #3542 was still blocked on an
  unresolved review thread, so local `main` lacked the change and the run
  re-applied the existing protection (a no-op). Apply only after confirming
  `git log -1` on `main` shows the merge.

### Step 10 deviation: TOML, not YAML (2026-10-08)

PyYAML isn't a direct dependency of the backend or web-server. It's declared
only in `tests/requirements-test.txt`, and the autonomy-matrix workflow doesn't
install that file. Locally it arrives transitively through
`kubernetes_asyncio`, so `--check` would pass locally and fail in CI with
`ModuleNotFoundError`.

The mapping is therefore `docs/compliance/control-objectives.toml`, read with
the stdlib `tomllib` (Python 3.12). There's no new dependency and no workflow
change, and it's still human-editable with comments. Everything else in step 10
is unchanged.

### Steps 10–12: PR 2 (2026-10-08)

- **Step 10:** coder; mapping reviewed by the session model.
  - `docs/compliance/control-objectives.toml` has 12 entries, matching the 12
    derived ids.
  - The branch-protection claim is verbatim on `policy.tier.*` and `gate.*`.
  - Framework vocabulary is the hub's, and the SEC column is omitted.
  - **ISO A.5.23 was removed by the session model:** it covers the use of cloud
    services, not a model-assisted gate, even though the hub's #323 row cites
    it. The reason is in the TOML header.
  - **Orphans, both directions:** deleting an entry gives exit 1, naming
    `policy.val_floor`; a bogus entry gives exit 1, naming `bogus.x`.
- **Step 11:** `draft: true` was removed and the sidebar entry added.
  - The local `npm ci && npm run build` first **failed on our page**: the
    HTML-comment banner and `<br>` are invalid MDX, which `draft: true` had hidden
    in PR 1. These are now an MDX comment and `<br/>`, and the build passes.
- **Step 12:** AIFactory#1657 → `dev` @ `46c9e51f`, with 52 checks passing.
  - Copilot found that a non-table entry crashed with a traceback and that a
    non-string `claim` was published. The session model fixed both as named
    errors, with 2 tests that fail when the fix is reverted.
  - 20 generator tests.
- **Still to do:**
  - **Publication:** happens on the next AIFactory `release/*` → `main` merge.
  - **Step 13:** the hub links are staged on Factory branch
    `docs/1962-control-matrix-links` (`4dfdb6ee`). Merge them once
    `https://olafkfreund.github.io/AIFactory/compliance/autonomy-matrix`
    returns 200.
  - **Afterwards:** close #1962 and comment on #1958 and #1963.
