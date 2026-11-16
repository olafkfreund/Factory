---
status: draft
issue: 324
spec: spec/2026-11-16-324-audit-readiness.md
coders:
  1: lead   # judgement on what the evidence proves; no external implementer
  2: lead
  3: lead
  4: lead
reviewers:
  - codex   # read-only final review, `codex review --base origin/main`
---

# Plan: Audit-readiness checklist, mock-audit plan, stale compliance text

Approved decisions (spec): add `docs/compliance/audit-readiness.md` (checklist, mock-audit
plan, owner actions), correct stale prose only where evidence proves it, add one test. No
SoA/SOC 2 rating changes; no edits to alerting/IR/key-expiry text; SoA and risk-register backup
rows stay. All paths below are under the Factory worktree.

## Steps

1. `docs/compliance/audit-readiness.md` (new): three sections.
   - Checklist table, columns item | status | evidence | tracker | owner. Status is one of
     `Ready`, `Open`, `Owner`. Rows and sources:
     policy set (`policies/information-security-policy.md`, Ready); SoA
     (`statement-of-applicability.md`, Ready); risk register (`risk-register.md`, Ready);
     roles (`roles.md`, Ready); control matrix (`control-matrix.md`, Ready); SOC 2 gap
     assessment (`soc2-gap-assessment.md`, Ready); residual-risk sign-off (same file,
     Owner, table unsigned); management review held and independent review (#3694, Open,
     `management-review-and-internal-audit.md`); security awareness record (#3693, Open,
     `training-and-awareness.md`); supplier records (#3695, Open, `supplier-management.md`);
     backup and restore evidence (`dr-runbook.md`, `dr-restore-drill.yaml`, Open: off-cluster
     copy #3681, MinIO backup and re-drill #3691); evidence collection and retention
     (`evidence-collector` CronJob, Open: code-scanning snapshot needs the secret, Owner;
     retention floor #3692 closed); vulnerability SLA and register (`remediation-sla.md`,
     `vulnerability-register.md`, Ready); IR tabletop (`ir-tabletop.md`, Owner: not run,
     #3688); authority contact list (#3698, Open); framework applicability SEC/NYDFS/FFIEC/SOX
     (#3697, Open, `nydfs-part500-mapping.md`); PCI (`control-matrix.md` says scoped out,
     Ready).
   - Mock-audit plan: cites `management-review-and-internal-audit.md` section 2 for scope,
     independence, report template and "First audit"; adds the sample (SoA A.8.13, A.5.28;
     SOC 2 CC6), evidence pulls with `mc` as in factory-gitops `docs/evidence-collection.md`
     ("How an assessor retrieves a control's evidence"): `mc cat fac/factory-evidence/<date>/backups-index.json`
     (backup operated), `mc cat fac/factory-evidence/<date>/audit-anchor.json` (chain),
     `mc ls fac/factory-evidence/control-plane-push/access-review/` (access review),
     `mc ls fac/factory-evidence/control-plane-push/codeql/`; pass criteria: each sampled control
     has dated operating evidence (not only a manifest), and missing evidence is recorded as a
     finding; findings go to
     `risk-register.md`/`remediation-sla.md`; and states "not held".
   - Owner actions: `kubectl -n factory create secret generic evidence-github-token
     --from-literal=token=<PAT>` (value supplied by the owner, never committed); sign the
     residual-risk table; decide mock-audit date and independent reviewer (decision);
     CI scan-upload wiring (decision: S3 credentials in CI, since the in-cluster MinIO is not
     reachable from runners): the push contract is
     `mc cp trivy.json fac/factory-evidence/control-plane-push/trivy/<repo>-<YYYY-MM-DD>.json`
     and `.../codeql/<repo>-<YYYY-MM-DD>.sarif`, from the #324 comment of 2026-07-25.
   Verify: step 3 test. Traps: no secret values; link paths relative to `docs/compliance/`.
2. Stale prose, each edit followed by a re-grep that the old phrase is gone:
   - `policies/data-governance.md`: intro (lines 19-23), Gaps 1 and 2 (lines 187-193), the
     two acceptance boxes for classification and scrub default (lines 241-244), evidence
     row "default off" (line 259) -> default on (`providers/__init__.py`
     `_env_scrub_outbound_default`, AIFactory#1128), classification in
     `policies/data-classification-and-handling-policy.md`. Keep the redactor fail-open note.
   - `policies/governance-isms.md`: mark G1-G4 closed with links (policy set, `roles.md`,
     `risk-register.md`, SoA); G1 keeps "no acknowledgement or review record"; note that
     "Current state" is the 2026-07-24 baseline.
   - `policies/business-continuity-policy.md` lines 33, 38, 73: daily in-cluster `pg_dumpall`
     CronJob `postgres-backup` exists (`dr-runbook.md`); off-cluster copy and MinIO backup
     still open (#3681, #3691).
   - `roles.md` row "Backup success / restore test" and `README.md` Wave 2 backup bullet:
     same correction.
   - `statement-of-applicability.md` A.5.5 -> #3698, A.5.35 -> #3694 (text only, ratings kept).
   Traps: do not touch `audit-logging.md`, `incident-response-policy.md`, R-001/R-009 rows.
3. `tests/test_audit_readiness.py` (new): parse the page; assert relative links and backticked
   `docs/`, `tests/`, `scripts/` paths exist, tracker links match
   `github.com/olafkfreund/<repo>/issues/<n>`, statuses in {Ready, Open, Owner}. Verify:
   `python -m pytest tests/test_audit_readiness.py tests/test_control_catalog.py -q`.
4. `docs/compliance/README.md`: add `audit-readiness.md` to the index. Verify: step 3 test and
   `ruff check tests/test_audit_readiness.py`.

## Tests

`python -m pytest tests/test_audit_readiness.py tests/test_control_catalog.py -q` passes;
`ruff check` and `ruff format --check` on the new test; repo CI docs checks green on the PR.

## Rollback

Revert the PR; docs and one test only, nothing is deployed.
