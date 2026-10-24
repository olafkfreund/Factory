# Gate at each inter-agent handoff

Factory#1963. The verify gate is model-assisted, so the deterministic checks
*between* agents matter. This page lists, for each handoff, what refuses a bad
payload where it is produced or received, and what does not.

Line numbers are at these default-branch commits and will drift: AIFactory
`1864519`, PFactory `0b6651d`, TFactory `17bc01d`. Paths are relative to each repo.

| Handoff | Verdict | Deterministic gate | Not covered |
|---|---|---|---|
| PFactory to AIFactory | Gated | Review gates, signed approval, signature + completeness + baseline checks | Key custody is per authority, not per plan |
| AIFactory to TFactory | Partial | Empty-build check on send, service token on receive | Contract signature and schema are never verified by TFactory (TFactory#1427) |
| TFactory to AIFactory | Partial | Member access, triage schema, confirm flag, assertion guard | A markdown-only handback skips schema validation (AIFactory#1858) |

## 1. PFactory to AIFactory (plan to build)

Sending side (PFactory, `apps/backend/`):

- `plan/review/models.py:118`: `gates_passed = all_pass and no_blockers`, arithmetic over deterministic lenses.
- `plan/review/approval.py:103-104`: signing raises `ApprovalError` when `gates_passed` is false, so an unreviewed plan carries no approval.
- `plan/emit/contract_emit.py:323-324` (docstring, enforced in `emit`): a contract that fails validation is never POSTed.

Receiving side (AIFactory):

- `apps/web-server/server/routes/execution.py:1383`: `verify_trusted_plan` runs before any allocation and returns 422 on failure.
- `apps/backend/trusted_plan.py:257` (`verify_plan_signature`), `:319` (`check_plan_completeness`), `:417` (both combined).
- `execution.py:1400`: baseline-drift gate refuses a plan approved against a different commit.

Verdict: gated, and refused at the boundary, before a spec directory exists.

## 2. AIFactory to TFactory (build to verify)

Sending side (AIFactory):

- `apps/web-server/server/services/completion_orchestration.py:42-76`: `_build_wrote_nothing` downgrades a build with zero commits to failed before the handoff.
- `apps/backend/pfactory/tfactory_client.py:768`: auth preflight can block the send (`enforce` mode only), a credentials check, not a content check.

Receiving side (TFactory):

- `apps/web-server/server/main.py:463`: `TokenAuthMiddleware`, service-level authentication.
- `apps/web-server/server/routes/specs.py:289-346`: path components sanitised, unparseable spec text rejected with 400.
- `apps/backend/agents/tools_pkg/tools/task_control.py:508-515`: the contract is written to `context/task_contract.json` once it has a `tfactory` or `contract_version` key. No signature check, no schema validation; `agents/task_contract.py:77` and `parse_tfactory_profile` tolerate missing and extra keys. The schema is only compared in CI (`tests/test_schema_drift.py:210`).

Verdict: partial. Anyone holding the service token can set the authoritative test profile. Filed as TFactory#1427.

## 3. TFactory to AIFactory (handback)

Sending side (TFactory): `apps/backend/agents/handback/send.py:45,222` stamps `contract_version` so the consumer can reject a shape it does not know.

Receiving side (AIFactory):

- `execution.py:1553-1557`: `apply-correction` needs task `member` access.
- `apps/backend/qa/correction.py:260-285`: a typed `triage` report is schema-validated and a malformed one stops the QA Fixer.
- `correction.py:110` (`check_fix_cycle_assertions`): after the fix cycle, flags tests that lost assertions, against a baseline taken at receipt.
- The `confirm` flag (`execution.py:112`) keeps a preview from writing.

Verdict: partial. Validation happens only when `triage` is present; a request with just `fix_request_md` reaches the fixer unvalidated. Filed as AIFactory#1858.

## The merge decision

Not a handoff, but the consumer of handoff 3's verdict: `apps/backend/merge/merge_policy.py:304-309` (`decide_merge`) auto-merges only when host CI, the TFactory verdict, the VAL floor and CI parity are all true. A permissive verdict cannot lift a red floor, because the checks are conjunctive. The mutation test #1963 asks for is not part of this survey.
