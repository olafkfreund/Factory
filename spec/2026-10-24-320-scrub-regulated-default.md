---
status: draft
issue: 320
intent: intent/2026-10-24-320-scrub-regulated-default.md
---

# Spec: outbound PII scrub is mandatory for regulated projects

AIFactory paths are at `origin/dev` 717feb4b; Factory paths at `origin/main` 24343dd.

## Design

### AIFactory: one switch, one new input

The scrub already has one resolver, `core/outbound_scrub.py:45 scrub_outbound_enabled()`,
used by the Claude SDK proxy (`_ScrubbingClient.query`), by `providers/__init__.py:81
_env_scrub_outbound_default()` and by the insights strategies
(`insights_providers/base.py:106`). The design adds one input to it, the project's data
class, carried in the env key `AIFACTORY_DATA_CLASSIFICATION`:

- New `scrub_outbound_required(classification: str | None = None) -> bool` in
  `outbound_scrub.py`: True iff the class (argument, else the env key, else `internal`)
  is `regulated`, case-insensitive.
- `scrub_outbound_enabled(classification=None)` returns True when
  `scrub_outbound_required(classification)`; otherwise today's kill-switch logic, unchanged.
- `BaseLLMProvider` wrapper (`providers/__init__.py:167-169`): an adapter's own
  `_scrub_outbound` pin (e.g. `OpenAICompatibleProvider(scrub_outbound=False)`, which also
  snapshots the kill-switch at construction, `openai_compatible.py:212-216`) is ignored when
  `scrub_outbound_required()` is True.
- The fail-closed error text (`outbound_scrub.py:107`) gains "not honoured for regulated
  projects" so the operator hint is not wrong for them.

### How the class reaches each egress path

The class is a per-project setting in the existing settings store
(`project_settings_store`), so it is never read from the agent-writable clone.

- API: `routes/projects.py` `ProjectSettingsUpdate` gains
  `dataClassification: Literal["public","internal","confidential","regulated"] | None`
  (alias `data_classification`); `env_mapping` maps it to `AIFACTORY_DATA_CLASSIFICATION`.
  Pydantic rejects other values (422). Unset means `internal`; nothing is written for it.
- Allowlist: `project_env.py PROJECT_ENV_KEYS` gains `AIFACTORY_DATA_CLASSIFICATION`, so
  `load_project_env()` copies it into the child env of agent builds
  (`agent_service.py:1129`), spec creation (`agent_spec_creation.py:243`) and PR review
  (`pr_review_service.py:277`) with no change at those call sites. Inside the child, the
  backend resolver reads it from `os.environ`.
- New helper `project_settings_store.data_classification(project_path) -> str`: the
  stored value, `internal` if unset, and `regulated` if the store cannot be read, so an
  unreadable store fails closed (scrub on).
- Changelog runner spawn (`changelog_service.py:215`) builds its env with
  `make_subprocess_env()` and no project settings; it sets the one key from the helper.
- Insights chat runs in the web-server process, which serves many projects, so the env
  cannot carry the class. The `send_message` wrapper (`insights_providers/base.py:159`)
  already receives `project_path`; it calls the helper and passes the result to
  `scrub_insights_outbound(..., classification=...)`, which passes it to
  `scrub_outbound_enabled(classification)`.

Tiers `public`, `internal`, `confidential` behave exactly as today. No UI change.

### Factory: policy text matches the code

- `data-classification-and-handling-policy.md` statement 2: the scrub is on by default on
  every AIFactory LLM path and fails closed; `LITELLM_AUDIT_SCRUB_OUTBOUND=false` turns it
  off deployment-wide except for projects with `dataClassification: regulated`, where it
  cannot be turned off. Statement 6: DSAR/per-record erasure is out of scope (decision
  2026-10-24) because no PII is in scope today; trigger to bring it back: the first
  project classified `regulated`, any feature that stores personal data on purpose, or a
  data-subject request received.
- `data-governance.md`: "Redaction posture" paragraph (lines 59-68) restated to the real
  posture; Regulated row (line 181) says "DSAR/erasure supported" and becomes "DSAR/erasure
  out of scope until the trigger in the policy"; "What is missing" item 5 and the Phase 3
  / checklist DSAR lines point at the decision.
- `risk-register.md` R-004 and `statement-of-applicability.md` A.8.11 / A.5.34: drop the
  stale "off by default" wording.

## Alternatives rejected

- **Make scrub opt-in for non-regulated tiers** (literal reading of "other tiers keep
  today's opt-in"): today is default-on; flipping it would weaken a shipped control.
- **Per-adapter / per-call classification argument**: about 20 Claude SDK call sites and
  every adapter would need threading; the env key reaches them all through the one resolver.
- **Read the class from `.aifactory/` in the clone**: agent-writable, so an agent could
  downgrade its own project (#1795 moved settings out for this reason).
- **Store the class in `projects.json` only**: does not reach child processes.
- **Classification in the deployment (Helm) values**: one class for all projects; does
  not express a mixed fleet. Still possible by setting the env key deployment-wide.
- **Route regulated projects to a LOCAL model automatically**: larger change, a provider
  policy decision, not asked.

## Risks

- **Deployment-level env masks the project value.** `load_project_env` never overrides a
  key already in the child env. An operator who sets `AIFACTORY_DATA_CLASSIFICATION` to a
  non-regulated value deployment-wide would mask a regulated project. Documented in the
  policy; do not set it deployment-wide except to `regulated`.
- **Spawns without the class.** `clarification_service.py:197` and
  `insights_service.py:540` call the `claude` CLI directly with a prompt and are not
  scrubbed at all today, for any tier. Pre-existing gap of #1128 coverage, out of this
  scope; a follow-up issue is filed and named in the policy as a known exception.
- **Admin downgrade.** A project admin can change the class; that is the classification
  owner's decision, logged by the existing settings write path.
- **Prompt quality.** Regulated projects lose the kill-switch; the scrub is the
  high-precision built-in set (#1010), so code prompts are not corrupted.
- **Insights store read per message.** One settings read per chat message; it is a
  cached store read, acceptable.

## Verification

- Backend tests (`tests/test_outbound_scrub_all_providers.py`): regulated + kill-switch
  off -> adapter and SDK proxy send scrubbed; internal + kill-switch off -> raw (unchanged);
  unset class + unset switch -> scrubbed (existing); regulated +
  `OpenAICompatibleProvider(scrub_outbound=False)` -> scrubbed.
- Web-server tests: `AIFACTORY_DATA_CLASSIFICATION` passes `is_project_env_key`;
  PATCH `dataClassification: regulated` stores the key, an invalid value is 422;
  `data_classification()` returns `internal` unset, `regulated` on store error; insights
  regulated + kill-switch off -> wire scrubbed, internal + kill-switch off -> raw.
- Existing scrub, settings and insights suites stay green.
- Factory: hooks pass; `grep -n "opt-in\|off by default\|defaults to .False" ` on the
  touched docs returns no stale claim about the outbound scrub.
