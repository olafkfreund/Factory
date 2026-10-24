---
status: draft
issue: 320
spec: spec/2026-10-24-320-scrub-regulated-default.md
---

# Plan: outbound PII scrub is mandatory for regulated projects

Worktrees: AIFactory `fix/320-scrub-regulated-default` off `origin/dev` 717feb4b; Factory
`docs/320-scrub-regulated-default` off `origin/main` 24343dd (this file). Line numbers are
at those commits.

## Decisions (carried from the approved spec)

1. Today the outbound scrub is already ON by default on every AIFactory LLM path,
   fail-closed, with one deployment kill-switch `LITELLM_AUDIT_SCRUB_OUTBOUND=false`. Keep
   that unchanged for `public`, `internal`, `confidential`.
2. New project setting `dataClassification` (`public|internal|confidential|regulated`),
   default `internal` when unset, stored in the existing project settings store as env key
   `AIFACTORY_DATA_CLASSIFICATION`. No UI change.
3. `regulated` => scrub always on. The kill-switch and any adapter `_scrub_outbound` pin
   are ignored, because the policy's Regulated floor is "redact before third-party egress".
4. The class reaches child processes through `load_project_env` (allowlist entry) and the
   changelog spawn; the in-process insights chat reads it per call from the store.
   Unreadable store => `regulated` (fail closed).
5. DSAR / per-record erasure is out of scope (no PII in scope today). Trigger to bring it
   back: first project classified `regulated`, a feature that stores personal data on
   purpose, or a data-subject request received.
6. Known exception, not fixed here: `clarification_service.py:197` and
   `insights_service.py:540` call the `claude` CLI directly and are never scrubbed (any
   tier). File a follow-up issue; name it in the policy.

## Steps (AIFactory, one PR to `dev`)

1. `apps/backend/core/outbound_scrub.py:45-56`: add
   `scrub_outbound_required(classification: str | None = None) -> bool`
   (`(classification if classification is not None else os.environ.get("AIFACTORY_DATA_CLASSIFICATION", "internal")).strip().lower() == "regulated"`).
   Give `scrub_outbound_enabled` the same optional `classification` parameter and return
   True first when `scrub_outbound_required(classification)`. Add it to `__all__`
   (line ~158). At line 107-112 append "; not honoured for regulated projects" inside the
   parenthesised hint. Update the module docstring line "exactly ONE escape hatch" to say
   it does not apply to regulated projects.
   Verify: `apps/backend/.venv/bin/pytest tests/test_outbound_scrub_all_providers.py -q` still green.
   Traps: env read stays per call (no caching); `_ScrubbingClient.query` needs no edit.
2. `apps/backend/providers/__init__.py:167-169`: change
   `if enabled is None:` to `if enabled is None or scrub_outbound_required():`, with a lazy
   `from core.outbound_scrub import scrub_outbound_required  # noqa: PLC0415` inside the
   wrapper (same style as line 102). `_env_scrub_outbound_default()` then returns True.
   Verify: step 3's adapter-pin test.
   Traps: `OpenAICompatibleProvider` always sets `_scrub_outbound` to a bool at
   construction (`openai_compatible.py:212-216`), so without this edit it bypasses the rule.
3. `tests/test_outbound_scrub_all_providers.py`: in `_clean_env` (line 71-72) also
   `delenv("AIFACTORY_DATA_CLASSIFICATION")`. In `TestKillSwitch` (line 403) add:
   regulated + `LITELLM_AUDIT_SCRUB_OUTBOUND=false` -> `CopilotAgenticProvider` prompt has
   no `FAKE_SSN`; `internal` + kill-switch false -> raw (unchanged); regulated +
   `OpenAICompatibleProvider(..., scrub_outbound=False)` -> scrubbed (reuse the HTTP
   adapter setup in `TestHttpAdapters`, line 120); regulated + kill-switch false through
   `wrap_client_outbound_scrub(_RecordingSDKClient())` (line 247) -> scrubbed. Plus a
   unit test that `scrub_outbound_required("Regulated")` is True and `None`/`internal` False.
   Verify: `apps/backend/.venv/bin/pytest tests/test_outbound_scrub_all_providers.py -q`.
4. `apps/web-server/server/services/project_env.py:21-42`: add
   `"AIFACTORY_DATA_CLASSIFICATION",` under the `# routes/projects.py settings` block.
   Verify: `test_project_env.py` passes.
5. `apps/web-server/server/routes/projects.py`: next to line 39 add
   `DataClassification = Literal["public", "internal", "confidential", "regulated"]`;
   after line 876 add
   `dataClassification: DataClassification | None = Field(default=None, alias="data_classification")`
   with a one-line comment (#320, default internal when unset); in `env_mapping`
   (line 914-927) add `"dataClassification": "AIFACTORY_DATA_CLASSIFICATION",`.
   Verify: `test_project_env.py::test_writer_coverage` passes (it fails if step 4 is missing).
   Traps: do not add a validator that maps bad values to None (as `memoryBackend` does);
   a bad class must be a 422, not a silent no-op.
6. `apps/web-server/server/services/project_settings_store.py` after `get_settings`
   (line 375): add module-level
   `async def data_classification(project_path) -> str` returning
   `(await get_settings(project_path)).get("AIFACTORY_DATA_CLASSIFICATION", "internal")`,
   and `"regulated"` on any exception (log a warning with `sanitize_log`). Comment the why
   in one line: unreadable store must not lower the floor.
7. `apps/web-server/server/services/changelog_service.py:215`: after
   `env = make_subprocess_env()`, set
   `env["AIFACTORY_DATA_CLASSIFICATION"] = await project_settings_store.data_classification(project_path)`
   (import as the module already imports services; check the import style at the top).
8. `apps/web-server/server/services/insights_providers/base.py`: `scrub_insights_outbound`
   (line 74) gains keyword `classification: str | None = None` and calls
   `scrub_outbound_enabled(classification)` at line 106; the wrapper (line 159) first does a
   lazy `from server.services import project_settings_store` and passes
   `classification=await project_settings_store.data_classification(project_path)`.
   Traps: lazy import to avoid an import cycle; strategies are singletons, keep no state on `self`.
9. Web-server tests:
   - `apps/web-server/tests/test_project_settings_writers.py` (pattern at line 79):
     PATCH `dataClassification="regulated"` stores `AIFACTORY_DATA_CLASSIFICATION=regulated`;
     constructing `ProjectSettingsUpdate(dataClassification="secret")` raises `ValidationError`.
   - `apps/web-server/tests/test_project_settings_store.py`: `data_classification()` is
     `internal` when unset, the stored value when set, `regulated` when `get_settings` raises.
   - `apps/web-server/tests/test_insights_outbound_scrub.py`: add an autouse fixture that
     monkeypatches `project_settings_store.data_classification` to return `"internal"`
     (else the store is unreadable in tests, the class becomes `regulated`, and the existing
     kill-switch mutation test at line 240 fails). Add: class `regulated` + kill-switch
     false -> wire carries no PII; `internal` + kill-switch false -> raw (that is line 240).
   Verify: `cd apps/web-server && ../backend/.venv/bin/pytest tests/test_project_env.py tests/test_project_settings_writers.py tests/test_project_settings_store.py tests/test_insights_outbound_scrub.py tests/test_project_env_call_sites.py -q`
   (use the web-server's own test runner if its CI job differs; check `.github/workflows`).
10. File the follow-up issue in AIFactory for the unscrubbed `claude --print` spawns
    (decision 6), body ends with the session footer; put its number in the PR and step 12.
11. Open the AIFactory PR to `dev` linking the three Factory files; commit footer and PR
    footer per house rules. Never `--no-verify`.

## Steps (Factory, one PR to `main`, after step 11 so the code is real)

12. `docs/compliance/policies/data-classification-and-handling-policy.md`:
    statement 2 (lines 35-40): scrub on by default on every AIFactory LLM path, fails
    closed; `LITELLM_AUDIT_SCRUB_OUTBOUND=false` disables it deployment-wide except for
    projects with `dataClassification: regulated` (AIFactory project setting, default
    `internal`); do not set `AIFACTORY_DATA_CLASSIFICATION` deployment-wide except to
    `regulated`; known exception = follow-up issue from step 10; LOCAL-model sentence kept.
    Statement 6 (lines 53-56): decision 5 verbatim with date 2026-10-24.
13. `docs/compliance/policies/data-governance.md`: lines 59-68 restate the posture
    (default-on since AIFactory #1128, fail-closed, kill-switch, regulated rule; keep the
    audit-hook `_PassthroughRedactor` sentence only if still true at `llm_audit_hook.py:116`);
    line 138 "not changed here" -> point at the policy; line 181 Regulated row
    "DSAR/erasure supported" -> "DSAR/erasure out of scope until the policy trigger";
    item 5 (line 202), Phase 3 (line 234) and checklist (line 253): mark as deferred by the
    decision, keep the text of the gap.
14. `docs/compliance/risk-register.md:38` R-004: description no longer says redaction is
    off by default / fails open; controls add the regulated rule; status stays
    "In progress (Factory#320)" (sub-items of #320 remain). `statement-of-applicability.md`
    line 66 and 153: drop "PII-egress-by-default" / "outbound off-by-default".
    Verify 12-14: `git grep -n -i "off by default\|opt-in\|audit row only\|audit-row only" docs/compliance`
    shows no stale outbound-scrub claim; hooks pass.
    Traps: no secret values, no IPs, no names of people or organisations; cite AIFactory
    paths with the merged commit hash.
15. Comment on Factory#320 with both PR links; do not close it (classification of data
    assets beyond projects is still open).

## Tests

- AIFactory: `apps/backend/.venv/bin/pytest tests/test_outbound_scrub_all_providers.py tests/llm_gateway -q`
  and the web-server command in step 9: all green, new tests fail if steps 1/2/8 are reverted.
- `just test-backend` before pushing; pre-commit hooks on commit (can take 10+ minutes).
- Factory: pre-commit hooks pass.

## Rollback

Revert the AIFactory PR: the setting key becomes inert (unknown to the resolver), stored
values stay harmless in the store. Revert the Factory PR for the doc text.
