# E2E Campaign Fixtures

This directory holds the project fixtures for the Factory end-to-end test campaign (`plan/2026-11-24-3882-e2e-campaign.md`). The companion hidden acceptance suites live in `tests/e2e/hidden/P#/` and are never pushed to the test repositories.

## Directory Layout

Each fixture `tests/e2e/fixtures/P#/` has three subdirectories:

- `starter/`: The initial repository tree pushed to `Freundcloud/e2e-<yyyymmdd>-P#-<run>` at the start of a journey. It is a minimal runnable project with `pytest`, where the target feature is unimplemented (`NotImplementedError`) so its own visible tests fail until the coding agent implements the feature.
- `triple/`: The approved artifact-workflow files plus the execution profile:
  - `intent/<slug>.md` (`status: approved`)
  - `spec/<slug>.md` (`status: approved`, linking `intent/<slug>.md`)
  - `plan/<slug>.md` (`status: approved`, linking `spec/<slug>.md`)
  - `execution.json`: The Task Contract v2 `execution` block consumed by AIFactory's `/api/tasks/from-plan` (`create_from_trusted_plan` -> `ingest_trusted_plan` -> `apply_execution_profile`). It sets different Claude models for the coder (`coding`: `claude-sonnet-4-6`) and the QA reviewer (`qa`: `claude-opus-4-7`).
- `reference/`: A clean overlay of the reference solution. Copying `reference/` over `starter/` produces a passing repository for positive fixtures (`P1`).

### Trusted-plan `execution` field names (AIFactory `execution.py` / `trusted_plan.py`)

AIFactory's `POST /api/tasks/from-plan` (`create_from_trusted_plan` in `apps/web-server/server/routes/execution.py`) accepts `FromPlanRequest(plan=..., provenance=...)` and passes `request.plan` to `ingest_trusted_plan` (`apps/backend/trusted_plan.py`).

- `ingest_trusted_plan` calls `apply_execution_profile(spec_dir, plan)`, which reads `plan["execution"]` and translates snake_case Task Contract v2 keys into camelCase `task_metadata.json` keys via `_EXECUTION_TO_METADATA`:
  - `phase_models` -> `phaseModels` (keys: `spec`, `planning`, `coding`, `qa`, `qa_fixer`)
  - `phase_thinking` -> `phaseThinking`
  - `model` -> `model`, `runtime` -> `runtime`, `parallel` -> `parallel`, `workers` -> `workers`, `complexity` -> `complexity`, `review_tier` -> `reviewTier`, `skills` -> `selectedSkills`, `skip_planning` -> `skipPlanning`, `autonomy_tier` -> `difficultyTier`, `budget_usd` -> `budgetUsd`
  - Note: `provider` is emitted by PFactory in `plan["execution"]["provider"]`, and step 1b of the campaign plan adds `provider` mapping to `trusted_plan.py` if the step 0 probe shows provider routing needs it.
- To ensure `triple/execution.json` works whether a harness caller embeds it as `plan["execution"]` in a signed v2 contract (`phase_models`) or merges it directly into `task_metadata.json` (`phaseModels`), `execution.json` carries both `phase_models` and `phaseModels` (and both `phase_thinking` and `phaseThinking`) with identical values.

## Fixtures in Step 3

### `P1` — Python stdlib CLI `wordfreq` (XS canary)

- **Starter (`tests/e2e/fixtures/P1/starter/`):** `wordfreq` package (`wordfreq/cli.py`, `wordfreq/__main__.py`) with `count_words`, `format_table`, and `main` stubs raising `NotImplementedError`, plus 3 visible failing tests in `tests/test_wordfreq.py`.
- **Reference (`tests/e2e/fixtures/P1/reference/`):** Full stdlib implementation of `wordfreq/cli.py` and expanded visible tests in `tests/test_wordfreq.py`.
- **Hidden suite (`tests/e2e/hidden/P1/test_hidden_wordfreq.py`):** 7 tests covering punctuation tokenization, alphabetical tie-breaking, case sensitivity, `--min-len`, `--top`, `ValueError` validation, `stdin` (`-`) with `--json`, empty-input TSV behavior, error exit code `2`, and `python -m wordfreq` subprocess execution.

### `P5` — Contradictory criteria trap `vatcalc` (XS negative trap)

- **Purpose:** Must fail PFactory review (`criteria-self-consistent` / `red-team`) or stop in AIFactory `Needs you`.
- **Contradiction in `triple/`:**
  1. Criterion A requires the additive invariant `total = net + vat` (`11.75` when `net = 10.00` and `vat = 1.75`), synchronous execution, and `vat_rate` required.
  2. Criterion B requires that for `net = 10.00` and `vat = 1.75`, `total = 11.76` and `total` must not equal `net + vat`, asynchronous execution, and `vat_rate` optional.
  3. Criterion C requires a single call `compute_quote("10.00", "0.175")` to return a `Quote` whose `total` is simultaneously equal to `Decimal("11.75")` and `Decimal("11.76")`.
- **Why `tests/e2e/hidden/P5/test_hidden_contradiction.py` cannot be satisfied:** The hidden test calls `quote = compute_quote("10.00", "0.175")` once, verifies `type(quote.total) is Decimal` (preventing custom `__eq__` spoofing), and asserts both `quote.total == Decimal("11.75")` and `quote.total == Decimal("11.76")` on that single `Decimal` instance. Because `Decimal("11.75") != Decimal("11.76")`, no Python implementation can ever pass the P5 hidden suite.

## Verifying a Fixture Locally

Always verify fixtures in a temporary directory so the fixture trees remain clean:

```bash
tmpdir="$(mktemp -d)"
trap 'rm -rf "$tmpdir"' EXIT

# 1. P1 starter alone must fail the P1 hidden suite
cp -a tests/e2e/fixtures/P1/starter "$tmpdir/p1-starter"
cp -a tests/e2e/hidden/P1 "$tmpdir/p1-starter/hidden"
PYTHONPATH="$tmpdir/p1-starter" python -m pytest "$tmpdir/p1-starter/hidden"

# 2. P1 starter + reference overlay must pass both visible and hidden suites
cp -a tests/e2e/fixtures/P1/starter "$tmpdir/p1-ref"
cp -a tests/e2e/fixtures/P1/reference/. "$tmpdir/p1-ref/"
cp -a tests/e2e/hidden/P1 "$tmpdir/p1-ref/hidden"
PYTHONPATH="$tmpdir/p1-ref" python -m pytest "$tmpdir/p1-ref/tests" "$tmpdir/p1-ref/hidden"

# 3. P5 hidden suite must fail on both P5 starter and P5 starter + reference
cp -a tests/e2e/fixtures/P5/starter "$tmpdir/p5-ref"
cp -a tests/e2e/fixtures/P5/reference/. "$tmpdir/p5-ref/"
cp -a tests/e2e/hidden/P5 "$tmpdir/p5-ref/hidden"
PYTHONPATH="$tmpdir/p5-ref" python -m pytest "$tmpdir/p5-ref/hidden"
```
