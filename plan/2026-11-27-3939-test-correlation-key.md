---
status: approved
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

The spec, copied here so this plan stands alone, with the plan review folded in (see "Review"
below).

- **Validator:** one helper in `shared/factory-cli/factory_cli/testrun.py`,
  `validate_correlation_key(value: str | None) -> str | None`.
  - It returns `value` unchanged when `value is None`. That means no key; `None` is the only
    "absent" value.
  - It raises `InputRejectedError("--correlation-key is not a valid correlation key")` unless
    `value` is a `str` that `_KEY.fullmatch`es and is not `isdigit()`.
    `_KEY = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:/#-]{0,127}")`, so `""` is invalid.
- **Validate before anything else, on both entry points:**
  - **CLI:** `__main__._dispatch_command` (~207) calls it for `cmd == "test"` **before**
    `collect_known_secrets` and `resolve_portal_key`, and exits with the CLI's precondition code.
  - **`run_test`** (~266) calls it as its first statement, before `collect_known_secrets` (~277).
    On a rejection it returns `_rejected_test(msg, exit_code=EXIT_PRECONDITION)` with the default
    `secrets=()`.
  - So a bad key never triggers a secret collection, a portal lookup, git or a request. The MCP
    serializer runs after `run_test`, and it is fine there because nothing was fetched.
- **Ingest body** (~315): a valid key adds `"correlation_key": key`. `None` leaves the body
  byte-identical.
- **CLI flag:** `__main__.py` (~79–86) gets
  `test_p.add_argument("--correlation-key", dest="correlation_key", default=None, help=…)`,
  passed at ~225.
- **MCP:** `mcp_server.py` changes in three places:
  - `handle_factory_test` (~88) gains `correlation_key: str | None = None` and passes it through;
  - the registered `factory_test` wrapper (~192–205) gains the same, which drives the MCP schema;
  - its description (~221–228) names the argument.
- **Harness:** `scripts/e2e/stages.py`.
  - `test(self, full_name, sha, _surface, correlation_key=None)` (~264) appends
    `["--correlation-key", key]` to the argv and `"correlation_key": key` to the MCP args when
    `key is not None`.
  - The protocol at ~391 matches.
  - The S5 call (~561) passes `state.get("correlation_key")`. S2 (~522) already stores it from
    either surface's submit output.

## Review (plan draft, 2026-11-27)

Codex (gpt-6.2-sol) and agy (model not reported) reviewed the draft. Both were read-only, and the
worktree was unchanged.

| Finding | Verdict | Change |
|---|---|---|
| The CLI collects secrets and resolves the portal key before `run_test` validates (both, high) | confirmed (`__main__.py:207-214`, `testrun.py:277`) | validator in `_dispatch_command` and first in `run_test`; `secrets=()` |
| The MCP registration and schema are untested (both) | confirmed | a test on the registered tool |
| Empty string versus absent (both) | confirmed | `None` is the only absent value, and `""` is invalid |
| The submit-to-test handoff is untested per surface (Codex) | confirmed | a CLI and an MCP case starting from the submit output |
| Anchors: body at ~315, description at ~221 (Codex) | confirmed | updated |

## Steps

1. **Codex:** `testrun.py`, `__main__.py`, `mcp_server.py`, plus tests in
   `shared/factory-cli/tests/test_factory_cli.py`, next to `test_factory_test_ingest_and_404_parity`
   (~633):
   - a valid `pf-337-x` appears in the posted body;
   - with no key, the body has no `correlation_key`;
   - `"42"`, `""`, `"a b"` and 129 characters are each refused. On both the CLI dispatch path and
     `handle_factory_test`, assert that no secret collection, no portal key resolution and no
     transport request happened. Use the module's existing fakes and spies;
   - the registered MCP `factory_test` tool, from `build_mcp_server()`, advertises an optional
     `correlation_key` and accepts a call with it;
   - `--correlation-key` parses and reaches `run_test`.

   **Verify:**
   ```bash
   cd shared/factory-cli && /mnt/code/Source-home/GitHub/AIFactory/apps/backend/.venv/bin/python -m pytest -q tests/test_factory_cli.py
   ```
   Then run `ruff check` and `ruff format --check` on the changed files.

2. **agy:** `scripts/e2e/stages.py` per the harness decision, plus tests in
   `tests/e2e/unit/test_wiring.py`:
   - the CLI argv and MCP args carry the key;
   - with `None`, both are unchanged;
   - S5 passes the state key;
   - one case per surface starts from that surface's `submit` output carrying `correlation_key`,
     and checks that the same key reaches the `test` request.

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

## Deviations (diff review, 2026-11-27)

- **No code change.** Codex found no issues. The fresh Opus review and agy both noted that the
  MCP response serializer (`dump_mcp_json`) still reads local key files for redaction after a
  rejected key. The plan allows this, because nothing is fetched. The rejection test stubs the
  serializer, so a comment now says it isolates `run_test` and does not prove that nothing is
  read.
- **Open:** the schema test uses a fake server, not the real MCP SDK schema. It is left as a
  coverage gap, and the live P1 run exercises the real MCP surface.
