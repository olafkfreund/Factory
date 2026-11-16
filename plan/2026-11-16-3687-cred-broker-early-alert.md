---
status: draft
issue: 3687
spec: spec/2026-11-16-3687-cred-broker-early-alert.md
coders:
  1: lead   # small tricky logic in one script block; a handoff costs more than it saves
  2: lead   # 6-line env addition
  3: lead   # doc edit
  4: lead   # tests exercise step 1, written with it
reviewers:
  - codex   # final diff review
  - agy     # final diff review
---

# Plan: cred-broker raises the issue on the first rejected refresh

Repo for all edits: olafkfreund/factory-gitops, branch `fix/3687-cred-broker-early-alert`
off `origin/main`. Approved decisions (spec): the broker files its own GitHub issue
(label `cred-broker`, marker `<!-- cred-broker:alert -->`), not adopted by job-watchdog.
Triggers: `invalid_grant` (past the >30d exemption), `no-refresh-token` (short
runway): always. Other failures (`http_*`, `bad-refresh-response`, network/`ValueError`):
when the token has at most `ALERT_WITHIN_HOURS` (default 5) left or expiry is unknown.
No token, or any GitHub error: log and keep the same exit code. The exemption for
more than 30 days stays. Do not touch `factory-cli-creds`, RBAC, or the watchdog.

## Steps

1. `apps/cred-broker/manifests/manifests.yaml`, `refresh.py` block (lines ~36-290):
   add `import os`; constants `ALERT_REPO`, `ALERT_WITHIN_HOURS` from env; add
   `alert(outcome, detail, exp_ms)` after `record()`: no `GITHUB_TOKEN` means log and
   return; ensure label (POST, ignore 422), GET open issues with the label, return if
   any body contains the marker, else POST title + body (marker first; outcome,
   detail, `access-expires-at` and hours left or "unknown", cause line, the re-seed
   steps with `--context k3d-factory`, `kubectl wait --for=condition=complete`
   before reading `last-outcome`, close-when-ok, watchdog note); whole function in
   `try/except Exception` logging the type only. Call it after `record()` in:
   `no-refresh-token` (always), `invalid_grant` (always), other `HTTPError` codes,
   and `bad-refresh-response` (window rule via a helper `within_window(exp_ms)`). Wrap
   the `urlopen`/`json.load` so `except HTTPError` stays first and a new
   `except (OSError, ValueError)` records `refresh-failed:network`, alerts by the
   window rule and returns 3. Check: step 4.
   Traps: indentation inside the YAML block scalar is 4 spaces; keep it stdlib-only;
   never print the token or response body; `iso(None)` must not be called.
2. Same file, CronJob container `refresh` (after `command:`): `env` with `GITHUB_TOKEN`
   from `factory-secrets/GITHUB_TOKEN` `optional: true`, and `ALERT_REPO`
   `olafkfreund/Factory`. Check: `python3 -c` YAML load of the file; manifest-validate
   workflow commands if available locally.
   Traps: no RBAC change; `factory-secrets` is read by the kubelet, not the SA.
3. `docs/secrets-management.md`: replace the 8 `--context factory` occurrences with
   `--context k3d-factory` (lines ~119, 279, 303, 345, 354, 363, 364, 374); add one
   paragraph under "Re-seeding the Claude OAuth credential" saying the broker files
   the issue (label `cred-broker`, body has outcome, expiry, steps), and add
   `kubectl wait --for=condition=complete job/cred-broker-verify` before the read in
   the verify step. Check: `grep -rn "context factory" docs/secrets-management.md`
   returns nothing. Other docs with the old context are listed in the PR, unchanged.
4. `.github/scripts/test_cred_broker.py`: extend `run()` to take `expires=` (None
   omits `expiresAt`), a network-error mode, an env dict for `GITHUB_TOKEN`, and a fake
   GitHub that records `(method, path)`; keep `m.record = cap`. Add the cases in
   spec Verification (invalid_grant 3h alerts with outcome/expiry in the body; 503 at
   3h alerts, at 50h does not; unknown expiry alerts; network at 3h alerts and exits 3,
   at 50h does not; existing marker issue means no POST; no token means no GitHub call;
   >30d exemption raises nothing; GitHub 500 keeps exit 3). Existing CASES must pass
   unchanged. Check: step run below.

## Tests

```
python3 .github/scripts/extract_embedded_script.py apps/cred-broker/manifests/manifests.yaml refresh.py /tmp/refresh_extracted.py
python3 .github/scripts/test_cred_broker.py        # all ok, "both directions correct"
python3 .github/scripts/test_extract_all_embedded.py
```
Plus the repo CI checks on the PR (manifest-validate, cred-broker test, job-watchdog selftest).
Mutation check: remove the `invalid_grant` alert call and see the test fail.

## Rollback

Revert the PR. The CronJob returns to its current behaviour; an issue the broker
already opened can be closed by hand. No cluster state is changed by this PR.
