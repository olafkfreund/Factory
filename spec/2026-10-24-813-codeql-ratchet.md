---
status: draft
issue: 813
intent: intent/2026-10-24-813-codeql-ratchet.md
---

# Spec: a CodeQL ratchet for the fleet

## Design

- `scripts/codeql_ratchet.py`: stdlib only. `gh api --paginate
  "repos/{repo}/code-scanning/alerts?state=open&per_page=100"` returns the open
  alerts. Each alert is bucketed by `rule.security_severity_level` when present
  (critical, high, medium, low), else by `rule.severity` (error, warning, note).
  Only the four tracked buckets count: critical, high, error, medium. Using one
  bucket per alert means a high security alert is not double counted as error.
- Baseline: `.github/codeql-baseline.json` in the caller, an object with the
  four keys. A missing key is a baseline of 0; a missing file is an error.
- Compare: for each tracked severity print `severity: current / baseline
  (+delta)`. Exit 1 if any current > baseline. Counts below baseline pass and
  print a hint to lower the baseline.
- `--self-test` covers bucketing and comparing without network, as
  check_deploy_drift.py does, and `tests/test_codeql_ratchet.py` runs it in hub CI.
- `.github/workflows/codeql-ratchet.yml`: `workflow_call`, permissions
  `security-events: read` and `contents: read`. It checks out the caller (for
  the baseline) and Factory (for the script, sparse) and runs the script with
  `GH_TOKEN`.
- Callers: `.github/workflows/codeql-ratchet.yml` in each of the four repos,
  weekly cron plus `workflow_dispatch`, `uses:
  olafkfreund/Factory/.github/workflows/codeql-ratchet.yml@main`, plus
  `.github/codeql-baseline.json` holding the live counts at PR time.

## Alternatives rejected

- Code scanning "alert threshold" in branch protection: gates PR alerts, not
  the standing backlog, and cannot be ratcheted per severity.
- One central job in Factory with a PAT: needs a cross-repo secret; the
  reusable workflow needs none.
- A script copy per repo: forks the logic (the Factory#483 defect).

## Risks

- `@main` pin means a bad Factory change breaks four weekly runs; same trade
  as deploy-drift, and the self-test runs on hub PRs.
- New alerts between baseline and merge make the first run red; the PR author
  re-reads the count and fixes the baseline.

## Verification

`python3 scripts/codeql_ratchet.py --self-test`, `pytest
tests/test_codeql_ratchet.py`, and a live dry run of the script against each
repo to produce the baseline.
