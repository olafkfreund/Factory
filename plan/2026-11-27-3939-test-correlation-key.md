---
status: draft
issue: 3939
spec: spec/2026-11-27-3939-test-correlation-key.md
coders:
  1: codex   # CLI option, validation and MCP twin: small, validation-sensitive
  2: agy     # harness wiring + unit tests: mechanical
reviewers:
  - codex    # independent read of validation and parity
  - agy      # second model (agent-team)
---

# Plan: `factory test` files its verify under the run's correlation key

## Approved decisions

The spec, copied here so this plan stands alone.

- **`run_test`:** `shared/factory-cli/factory_cli/testrun.py` `run_test` (~266) gains the keyword
  `correlation_key: str | None = None`.
  - Validate it first, before any key or portal lookup:
    `_KEY = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:/#-]{0,127}")` (`fullmatch`, and not
    `isdigit()`).
  - On a bad value, return `_rejected_test("--correlation-key is not a valid correlation key",
    exit_code=EXIT_PRECONDITION, secrets=secrets)`.
  - A valid value adds `"correlation_key": key` to the ingest body (~314). `None` leaves the body
    byte-identical.
- **CLI:** `__main__.py` (~79–86) gets
  `test_p.add_argument("--correlation-key", dest="correlation_key", default=None, help=…)`,
  passed at ~225.
- **MCP:** `mcp_server.py` `handle_factory_test` (~88) and the `factory_test` tool (~193) gain
  `correlation_key: str | None = None`, passed through. The tool's description lists the new
  argument.
- **Harness:** `scripts/e2e/stages.py`.
  - `test(self, full_name, sha, _surface, correlation_key=None)` (~264) appends
    `["--correlation-key", key]` to the argv and `"correlation_key": key` to the MCP args, only
    when `key` is truthy.
  - The protocol at ~391 matches.
  - The S5 call (~561) passes `state.get("correlation_key")`.

## Steps

1. **Codex:** `testrun.py`, `__main__.py`, `mcp_server.py`, plus tests in
   `shared/factory-cli/tests/test_factory_cli.py`, next to `test_factory_test_ingest_and_404_parity`
   (~633):
   - a valid key (`pf-337-x`) appears in the posted body;
   - with no key, the body has no `correlation_key`;
   - `"42"`, `"a b"` and 129 characters are each refused with no request made;
   - `handle_factory_test(..., correlation_key=…)` passes it through;
   - `--correlation-key` parses.

   **Verify:**
   ```bash
   cd shared/factory-cli && /mnt/code/Source-home/GitHub/AIFactory/apps/backend/.venv/bin/python -m pytest -q tests/test_factory_cli.py
   ```
   Then run `ruff check` and `ruff format --check` on the changed files.

2. **agy:** `scripts/e2e/stages.py` per the harness decision, plus tests in
   `tests/e2e/unit/test_wiring.py`:
   - the CLI argv and MCP args carry the key;
   - with no key, both are unchanged;
   - S5 passes the state key.

   **Verify:**
   ```bash
   /mnt/code/Source-home/GitHub/AIFactory/apps/backend/.venv/bin/python -m pytest -q tests/e2e/unit
   ```
   Then run `ruff check` and `ruff format --check`.

**Traps:**
- `stages.py` has `print` lines with `# noqa: T201`. Keep that pattern.
- The CLI test module builds its runtime with fake transports. Follow it; don't add network calls.

## Tests

- The verify commands above.
- CI green.
- Live, after the AIFactory and TFactory releases: a P1 run passes X.

## Rollback

Revert the PR. The option goes away, and the harness stops sending the key.
