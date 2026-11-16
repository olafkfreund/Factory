---
status: draft
issue: 1960
intent: intent/2026-11-16-1960-agent-attribution-signals.md
---

# Spec: agent and originator on every emitted signal and agent PR

## Design

One additive pair of keys, `agent_identity` and `originator`, each a string or
`null`, on every completion event. Values are copied exactly from where the
service already records them; nothing is invented or reformatted.

- **AIFactory** `server/services/completion.py`: new `_read_attribution(spec_dir)`
  (stdlib only, best-effort, never raises; the module is exec'd standalone, so no
  relative imports) reads `requirements.json` `originator` / `agent_identity`.
  `build_completion_event`, `build_worker_event` and `build_worker_progress_event`
  (each builds its own envelope) take both as keyword args (default `None`) and
  always set the two keys; the emitters `emit_terminal_completion`,
  `emit_usage_snapshot`, `emit_worker_completion` and `emit_worker_progress` pass
  `_read_attribution(spec_dir)`.
- **AIFactory PR body** `services/pr_endgame.py::_pr_title_body`: when
  `requirements.json` has values, append two lines
  `Authored by agent: <agent_identity>` and `Originator: <originator>`; each value
  is collapsed to one printable line (same rule as `core/commit_trailers.py`) and
  skipped if empty. PR author on GitHub stays the token owner (needs #1973).
- **AIFactory to TFactory** `pfactory/tfactory_client.py::build_ingest_payload`:
  add `originator` and `agent_identity` to the payload when set in `req`.
- **TFactory**: `SpecIngestRequest` gains optional `originator` and
  `agent_identity`; `create_spec_ingest_workspace` writes them into
  `context/source.json`; `_build_completion_envelope` reads them from the source
  meta and sets both keys (null when absent). `CompletionEnvelope` TypedDict gets
  the two fields.
- **PFactory** `plan/completion.py::build_completion_event`: set both keys from
  `session.originator` / `session.agent_identity` (already stamped at intake).
- **PFactory `agents/triager.py::_notify_completion`** (legacy flat callback with
  no attribution source in its status.json) is deliberately not changed: a
  permanently-null key would be noise. Recorded as a follow-up.
- **factory-gitops**: no change. `AIFACTORY_AGENT_COMMIT_TRAILERS` is already
  `"true"` (PR #326). The deployed image predates AIFactory#2015, so build Jobs
  honour it only after the next release; the live check that the agent can write
  the canonical spec dir in a build Job pod stays an owner/post-release action.

Pre-existing, out of scope: `completion.py` imports `.billing` relatively, so
the standalone exec in `agents/parallel_integration.py` fails and worker live
events never emit from there (Codex finding, to be filed as its own issue). The
new helper adds no relative import.

## Alternatives rejected

- Emit keys only when set (like `tenant_id`): the issue asks for the field
  "populated in every emitted run signature"; an explicit null is
  distinguishable from an emitter that never learned the field.
- Rewrite originators to `human:<provider>/<subject>`: changes existing values
  consumers already read; out of scope.
- Set the PR author via the API: needs a GitHub App credential (#1973).

## Risks

- Exact-dict assertions in existing tests of the three builders need the two
  new keys. Consumers that reject unknown keys: CFactory ingest is additive
  (RFC-0001 allows extra fields), verified by existing envelope tests.
- TFactory ingest is a contract surface: the new fields are optional.
- Handoff order: AIFactory may send fields to an older TFactory; Pydantic
  default ignores unknown keys, so it is safe either way.

## Verification

Per repo, unit tests: builder with and without values; `_read_attribution` on
missing/garbled file; PR body with values, empty and a newline-bearing value;
ingest request to `source.json` to envelope round trip in TFactory. Repo CI
lint and test suites for touched files; `codex review --base origin/<base>`.
