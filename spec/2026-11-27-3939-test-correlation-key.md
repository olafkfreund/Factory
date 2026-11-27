---
status: draft
issue: 3939
intent: intent/2026-11-27-3939-test-correlation-key.md
---

# Spec: `factory test` files its verify under the run's correlation key

## Design

- **`testrun.run_test`** (`shared/factory-cli/factory_cli/testrun.py:266`) gains the keyword
  `correlation_key: str | None = None`.
  - It is validated before any network call with `_KEY = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:/#-]{0,127}")`
    (`fullmatch`, and not all digits).
  - A bad value returns `_rejected_test(..., exit_code=EXIT_PRECONDITION)` with the message
    `--correlation-key is not a valid correlation key`.
  - A valid value is added to the ingest body as `"correlation_key"` (~314). When the value is
    `None`, the key is absent from the body.
- **CLI:** `__main__.py` (~79–86) gets
  `test_p.add_argument("--correlation-key", dest="correlation_key", default=None)`, passed at
  ~225.
- **MCP:** `mcp_server.py` `handle_factory_test` (~88) and the `factory_test` tool (~193) gain
  `correlation_key: str | None = None`, passed through.
- **Harness:** `scripts/e2e/stages.py`.
  - `test(self, full_name, sha, _surface, correlation_key=None)` (~264) appends
    `["--correlation-key", key]` to the CLI argv and `"correlation_key": key` to the MCP args, only
    when `key` is set.
  - The protocol at ~391 matches.
  - The S5 call (~561) passes `state.get("correlation_key")`.

## Alternatives rejected

- **The CLI looks the key up from PFactory:** `factory test` would need the session id and another
  service call. The caller already holds the key from `factory submit`.
- **Send a `contract` carrying the key:** TFactory treats any contract as an AIFactory handoff and
  changes the checkout (`_repo_binding`).

## Risks

- **A wrong key:** a caller with the wrong key mis-files the verify in CFactory. There is no gating
  effect.

## Verification

- **CLI tests** (`shared/factory-cli/tests/test_factory_cli.py`):
  - a valid key appears in the ingest body;
  - with no key, the body is unchanged;
  - an invalid key (digits, a space, 129 characters) is refused with no request;
  - the MCP handler passes the key through.
- **Harness unit tests** (`tests/e2e/unit/test_wiring.py`): `test()` puts the key on both
  surfaces, and leaves it out when there is none.
- **Checks:** the existing suites pass, ruff passes, and CI is green.
- **Live:** after AIFactory#2266 and TFactory#1713 are released, a P1 E2E run passes X.
