---
status: approved
issue: 312
spec: spec/2026-11-16-312-access-review-runbook.md
coders:
  # all steps by the lead (small, doc-heavy; a handoff would not repay its re-read)
  1: lead
  2: lead
  3: lead
  4: lead
  5: lead
reviewers:
  - codex   # independent read of the diff against this plan
---

# Plan: access-review runbook, role catalog and report generator

Carries the approved spec: slices H1-H3 of `plan/2026-10-27-312-fleet-rbac-role-model.md` (the role catalog, the runbook with its checks and exceptions, policy/matrix updates) plus `scripts/access_review_report.py`. AR ids are AR-004 (SoD) and AR-005 (wildcard exception) because AR-003 is held by an unsigned draft in `r007-ha-options.md`. Docs and a stdlib script only: no service, gitops or cluster change, no MFA enforcement. The generator takes a directory of read-only exports (files in the spec), treats a missing file as a finding, refuses (exit 2, no output) any input containing an `acw_[A-Za-z0-9]{8,}` string, checks every member (active or not) for 90-day inactivity, flags `Group` binding subjects for manual assessment, and takes `--now`.

## Generator contract (copied from the spec)

Input directory, every file optional (a missing file is the finding "input not provided: <file>"):

- \`members-<svc>.ndjson\`: lines \`{email, role, active, last_login_at, joined_at?, org_id?, tenant_groups?}\` (AIFactory \`/api/admin/access-review\`).
- \`keys.json\`: list of \`{key_id, owner, owner_role, scopes, autonomy_ceiling, last_used_at, expires_at, service}\`.
- \`cfactory-keys.json\`: list of \`{actor, scope}\`; \`write\` maps to \`member\`, \`read\` to \`viewer\`.
- \`bindings.json\`: list of \`{name, kind, subjects:[{kind,name}], justification}\`.
- \`keycloak-users.json\`: list of \`{username, enabled, mfa}\`; MFA is recorded, never enforced.
- \`platform-admins.json\`: list of \`{system, account}\`.
- \`legacy-counters.json\`: list of \`{name, count}\`, listed as evidence.
- \`exceptions.json\`: \`{wildcard_retirement_date}\`; absent or empty is a finding "date not set".

Checks (each one a finding line with the subject, never a secret): a key whose scopes exceed its owner's role (a \`viewer\` may hold only \`mcp:read\`); a member above \`viewer\`, active or not, with no login in 90 days or no \`last_login_at\`; an email with two roles in one org; \`tenant_groups\` present and not exactly one group (absent: "manual: tenant group not in export"); a key unused 90 days or with no \`expires_at\`; a null \`autonomy_ceiling\`; a binding with no justification or with a \`User\` subject (\`Group\` subject: "manual: assess members"); wildcard retirement date unset. Output \`review.md\` with sections Findings, Actions, Accepted exceptions (AR-004, AR-005, MFA not enforced), Signature (blank, signer: the owner, AR-004). Exit 2 and no output file if any input matches \`acw_[A-Za-z0-9]{8,}\`. \`--now YYYY-MM-DD\` fixes the clock; \`--in DIR --out FILE\`.

Test cases: every check fires once; a clean input yields no findings; each missing file yields its finding; a token-shaped string exits 2 and writes nothing; a disabled admin with no login is flagged.

Runbook content (step 2): cadence quarterly, due the 15th of the first month after quarter end (Q4 2026: 2027-01-15) and within five working days of anyone leaving or changing role; reviewer and signer the owner; revocations within five working days of signing, slower recorded as an exception with owner and date; read-only export commands per input; the guard \`grep -rE 'acw_[A-Za-z0-9]{8,}' <dir>\` must find nothing.

## Steps

1. `scripts/access_review_report.py` (new) and `tests/test_access_review_report.py` (new): implement the checks and the `review.md` renderer. → `pytest tests/test_access_review_report.py`; `ruff check scripts/access_review_report.py tests/test_access_review_report.py`.
   Traps: hub `scripts/` are covered by `uncollected-tests-allowlist.toml` and the banned-constructs lint; keep stdlib only, no `eval`/`subprocess`. Never print an input value in an error.
2. `docs/compliance/access-review-runbook.md` (new): cadence, inputs, checks, output path `factory-evidence/control-plane-push/access-review/<YYYY>-Q<n>/`, template, grep guard, generator usage. → `grep -n 'access_review_report' docs/compliance/access-review-runbook.md`.
3. `docs/compliance/rbac-role-catalog.md` (new): the catalog and action matrix; cite files verified with `git -C <repo> show origin/dev:<path>`. → each cited path resolves (listed in the PR).
4. `docs/compliance/risk-register.md`: AR-004, AR-005 rows and sections, accepted 2026-10-27, review 2027-04-27; recheck `main` and open PRs for the ids first. → `grep -n 'AR-004\|AR-005' docs/compliance/risk-register.md`; `grep -cE '^(\| |### )AR-002\b'` prints 1.
5. H3: `docs/compliance/policies/iam-access-control.md` (gaps 3-6 reflect the code), `control-matrix.md` IAM row, `README.md`, `roles.md` links; mkdocs nav if the site lists compliance pages. → `grep -n 'rbac-role-catalog' docs/compliance/policies/iam-access-control.md docs/compliance/control-matrix.md`; `mkdocs`-style link check used by hub CI.

## Tests

`pytest tests/test_access_review_report.py`; hub CI green on the head SHA.

## Rollback

Revert the PR. Docs and one unused script.
