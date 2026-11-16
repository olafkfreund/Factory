---
status: approved
issue: 3687
intent: intent/2026-11-16-3687-cred-broker-early-alert.md
---

# Spec: cred-broker raises the issue on the first rejected refresh

Code is in olafkfreund/factory-gitops. Paths below are relative to that repo.

## Design

`apps/cred-broker/manifests/manifests.yaml` (the `refresh.py` ConfigMap and the CronJob):

1. New `alert(outcome, detail, exp_ms)`, stdlib `urllib` like the rest of the script.
   Best-effort: any exception is logged by type only, and it never changes the
   exit code. With no `GITHUB_TOKEN` it logs "alerting inert" and returns.
2. First `POST /repos/{ALERT_REPO}/labels` for `cred-broker` (ignore 422), as job-watchdog does,
   so the label filter below cannot silently match nothing. Then `GET /repos/{ALERT_REPO}/issues?state=open&labels=cred-broker&per_page=100`. If any
   open issue body contains the marker `<!-- cred-broker:alert -->`, stop. Otherwise
   `POST` one issue, labelled `cred-broker` (GitHub creates the label on first use).
   Retries inside one Job (backoffLimit 2) run one after another, so
   list-then-create is enough. A hand-started `cred-broker-verify` Job can overlap a
   scheduled one; the guarantee is "no duplicates from the CronJob's own retries",
   and the worst overlap is one extra issue. The state is the open issue itself; nothing is
   stored in the Secret.
3. Title `cred-broker: Claude credential needs a re-seed (<outcome>)`. The body starts with
   the marker line, then, in this order: `last-outcome`, the fixed `last-detail`, `access-expires-at`
   and hours left, a one-line cause, the re-seed steps (copied from
   `docs/secrets-management.md`, with `--context k3d-factory`, no token on a
   command line), "close this issue once `last-outcome` is `ok`", and "job-watchdog may
   open its own staleness issue for the same fault". `alert()` is only ever given the fixed strings `record()` already writes (for example
   `HTTP 400 invalid_grant`, an exception class name), never a provider response
   body. The verify step uses `kubectl wait --for=condition=complete` before reading
   `last-outcome`, so an older `ok` is not mistaken for recovery.
4. Triggers, evaluated where the outcome is recorded today:
   - `refresh-rejected:invalid_grant` (already past the >30d exemption): always alert.
   - other `refresh-rejected:http_*`, and a new `refresh-failed:network` outcome for
     `OSError` (HTTPError is caught first), and `ValueError` from a non-JSON 200 (today these crash with no `record()`): alert when the
     access token has at most `ALERT_WITHIN_HOURS` left (default 5) or the expiry is
     unknown. The token lives 8h and the broker runs every 4h, so the first failed
     run sees at most 4h left and alerts at once; a lasting error is reported on
     the run that could still have helped, not after expiry.
   - `bad-refresh-response` (200 without tokens): same window rule as other errors.
   - `no-refresh-token` (short runway): always alert.
   - Network failure exits 3, as other refresh failures do (it was an uncaught exit 1).
5. CronJob env: `GITHUB_TOKEN` from `factory-secrets/GITHUB_TOKEN` with
   `optional: true`; `ALERT_REPO` default `olafkfreund/Factory`. RBAC unchanged.
6. `docs/secrets-management.md`: `--context factory` becomes `--context k3d-factory`
   (8 lines), and a short paragraph says the broker now files the issue.
7. `.github/scripts/test_cred_broker.py`: new cases with a fake `urlopen`/`k8s`:
   invalid_grant at 3h left alerts with outcome and expiry in the body; http_503 at
   3h alerts, at 50h does not; network error alerts and exits 3; existing open
   marker issue means no POST; no token means no HTTP call to GitHub; the long-lived
   exemption still raises nothing; a GitHub failure keeps exit 3. Unknown expiry (`expiresAt` absent) alerts for HTTP
   and network errors; a network failure with 50h left does not. `os.environ` is set per
   case, and each case asserts the exact list of GitHub requests (so a swallowed error
   inside `alert()` cannot pass a "no POST" check).

## Alternatives rejected

- Let job-watchdog raise it: it has no access to Secrets by design (no `secrets` in its
  ClusterRole), and its recovery logic closes any issue it owns after one failure.
- Reuse the watchdog marker so it adopts the issue: it would close the early alert
  within 30 minutes and then open a duplicate 4h later.
- A new Secret-annotation reminder or a day-10 timer: that is option 2, the owner's call.
- Changing the watchdog thresholds: affects every CronJob.

## Risks

- A transient outage with a 4h-old token raises one issue that turns out harmless.
  Accepted: one issue, closed by hand, and the body states the real outcome.
- Two issues for one fault when the watchdog later also fires (said in the body).
- `GITHUB_TOKEN` missing or lacking `repo` scope: broker still rotates and fails as
  before; the log says alerting was inert. The issue-raising path is untested live.
- An open issue nobody closes suppresses the next alert; the body says to close it.

## Verification

- `python3 .github/scripts/extract_embedded_script.py apps/cred-broker/manifests/manifests.yaml refresh.py /tmp/refresh_extracted.py` then `python3 .github/scripts/test_cred_broker.py` (as in CI).
- `kubectl kustomize apps/cred-broker/manifests` or the repo's manifest-validate workflow for the env change.
- No live run; the cluster is not touched.
