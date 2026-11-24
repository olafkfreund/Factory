# E2E Campaign Fixtures

This directory holds the project fixtures for the Factory end-to-end test campaign (`plan/2026-11-24-3882-e2e-campaign.md`). The companion hidden acceptance suites live in `tests/e2e/hidden/P#/` and are never pushed to the test repositories.

## Directory Layout

Each fixture `tests/e2e/fixtures/P#/` has three subdirectories:

- `starter/`: The initial repository tree pushed to `Freundcloud/e2e-<yyyymmdd>-P#-<run>` at the start of a journey. It is a minimal runnable project with `pytest`, where the target feature is unimplemented (`NotImplementedError`) so its own visible tests fail until the coding agent implements the feature.
- `triple/`: The approved artifact-workflow files plus the execution profile:
  - `intent/<slug>.md` (`status: approved`)
  - `spec/<slug>.md` (`status: approved`, linking `intent/<slug>.md`)
  - `plan/<slug>.md` (`status: approved`, linking `spec/<slug>.md`)
  - `execution.json`: Nested under the signed plan's `execution` block (`plan["execution"]`) when submitting to AIFactory's `/api/tasks/from-plan` (`create_from_trusted_plan` -> `ingest_trusted_plan` -> `apply_execution_profile`). It sets different Claude models for the coder (`coding`: `claude-sonnet-4-6`) and the QA reviewer (`qa`: `claude-opus-4-7`).
- `reference/`: A clean overlay of the reference solution. Copying `reference/` over `starter/` produces a passing repository for positive fixtures (`P1`).

### Trusted-plan `execution` field mapping (AIFactory `execution.py` / `trusted_plan.py`)

AIFactory's `POST /api/tasks/from-plan` (`create_from_trusted_plan` in `apps/web-server/server/routes/execution.py`) accepts `FromPlanRequest(plan=..., provenance=...)` and passes `request.plan` to `ingest_trusted_plan` (`apps/backend/trusted_plan.py`).

- `triple/execution.json` is nested under the signed plan's `execution` block (`plan["execution"]`).
- `ingest_trusted_plan` calls `apply_execution_profile(spec_dir, plan)`, which reads `plan["execution"]` and maps only the keys listed in `_EXECUTION_TO_METADATA` into `task_metadata.json`:
  - `phase_models`, `phase_thinking`, and `skip_planning` map to their camelCase metadata counterparts (`phaseModels`, `phaseThinking`, and `skipPlanning`).
  - `runtime`, `model`, `parallel`, `workers`, and `complexity` are preserved under the same key names.
- `provider` and duplicate camelCase keys are omitted from `triple/execution.json` because the trusted-plan mapper ignores them.

## Fixtures in Step 3

### `P1` — Python stdlib CLI `wordfreq` (XS canary)

- **Starter (`tests/e2e/fixtures/P1/starter/`):** `wordfreq` package (`wordfreq/cli.py`, `wordfreq/__main__.py`) with `count_words`, `format_table`, and `main` stubs raising `NotImplementedError`, plus 3 visible failing tests in `tests/test_wordfreq.py`.
- **Reference (`tests/e2e/fixtures/P1/reference/`):** Full stdlib implementation of `wordfreq/cli.py` and expanded visible tests in `tests/test_wordfreq.py`.
- **Hidden suite (`tests/e2e/hidden/P1/test_hidden_wordfreq.py`):** 9 tests covering punctuation tokenization, alphabetical tie-breaking, case sensitivity, `--min-len`, `--top`, `ValueError` validation, default `stdin` with `--json` and trailing newline, `--case-sensitive` CLI output with TSV trailing newline, empty-input TSV behavior, error exit code `2`, and `python -m wordfreq` subprocess execution.

### `P5` — Contradictory criteria trap `vatcalc` (XS negative trap)

- **Expected verdict (campaign-side only — never leaked in `triple/`):** The files under `tests/e2e/fixtures/P5/triple/` are written as an ordinary, sincere UK invoice VAT calculator request without mentioning that the criteria conflict. PFactory review (`criteria-self-consistent` / `red-team`) must reject the spec/plan, or AIFactory must stop the build in `Needs you`.
- **Mechanically detectable contradiction in `triple/spec/2026-11-24-5-vat-quote.md`:**
  1. Additive invariant bullet under `## Verification`: for every returned `Quote`, `quote.total == quote.net + quote.vat` (`Decimal("11.75")` when `net = Decimal("10.00")` and `vat = Decimal("1.75")`).
  2. Worked example bullet under `## Verification`: for `net = Decimal("10.00")` and `vat_rate = Decimal("0.175")`, `compute_quote("10.00", "0.175")` returns `quote.net == Decimal("10.00")`, `quote.vat == Decimal("1.75")`, and `quote.total == Decimal("11.76")`.
  3. Signature bullets under `## Verification`: one bullet requires `compute_quote(net, vat_rate)` to be synchronous (`def`) with `vat_rate` required; the next requires `compute_quote(net, vat_rate="0.175")` to be asynchronous (`async def`) with `vat_rate` optional.
- **Oracle mechanics (`tests/e2e/hidden/P5/test_hidden_contradiction.py`):** The hidden test calls `quote = compute_quote("10.00", "0.175")` once, captures `total = quote.total` once into a local variable, verifies `type(total) is Decimal` (preventing custom `__eq__` or stateful `@property` spoofing), and asserts both `total == quote.net + quote.vat` (`Decimal("11.75")`) and `total == Decimal("11.76")` on that single local `Decimal` value. Because `Decimal("11.75")` and `Decimal("11.76")` are distinct `Decimal` values, no Python implementation can pass the P5 hidden suite.

## Verifying a Fixture Locally

Always verify fixtures in a temporary directory so the fixture trees remain clean:

```bash
tmpdir="$(mktemp -d)"
trap 'rm -rf "$tmpdir"' EXIT

# 1. P1 starter alone must fail the P1 hidden suite
cp -a tests/e2e/fixtures/P1/starter "$tmpdir/p1-starter"
cp -a tests/e2e/hidden/P1 "$tmpdir/p1-starter/hidden"
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH="$tmpdir/p1-starter" uv run -q --with pytest python -m pytest -q -p no:cacheprovider "$tmpdir/p1-starter/hidden"

# 2. P1 starter + reference overlay must pass both visible and hidden suites
cp -a tests/e2e/fixtures/P1/starter "$tmpdir/p1-ref"
cp -a tests/e2e/fixtures/P1/reference/. "$tmpdir/p1-ref/"
cp -a tests/e2e/hidden/P1 "$tmpdir/p1-ref/hidden"
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH="$tmpdir/p1-ref" uv run -q --with pytest python -m pytest -q -p no:cacheprovider "$tmpdir/p1-ref/tests" "$tmpdir/p1-ref/hidden"

# 3. P5 hidden suite must fail on both P5 starter and P5 starter + reference
cp -a tests/e2e/fixtures/P5/starter "$tmpdir/p5-ref"
cp -a tests/e2e/fixtures/P5/reference/. "$tmpdir/p5-ref/"
cp -a tests/e2e/hidden/P5 "$tmpdir/p5-ref/hidden"
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH="$tmpdir/p5-ref" uv run -q --with pytest python -m pytest -q -p no:cacheprovider "$tmpdir/p5-ref/hidden"
```
