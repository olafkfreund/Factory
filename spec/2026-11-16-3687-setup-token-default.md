---
status: draft
issue: 3687
intent: intent/2026-11-16-3687-setup-token-default.md
---

# Spec: setup-token as the default Claude credential flow

## Design

1. `docs/secrets-management.md`: the flow table (section "Re-seeding the Claude OAuth credential") lists
   `claude setup-token` first and marks it the default; `auth login` is the alternative
   (about 30 days, then re-login). The procedure is rewritten for setup-token: mint the
   token, patch both Secrets (`factory-cli-creds` as a file with only `accessToken`,
   `expiresAt` set 360 days out, scope `user:inference`; `factory-secrets`
   `CLAUDE_CODE_OAUTH_TOKEN`), update the agenix slot so it survives a reboot, run a fresh
   verify Job (expect `not-applicable:long-lived-credential`), restart the consumers
   (cred-sync refuses a seed more than 90 days fresher than the file in the pod), check
   TFactory `/api/health` for `validity: valid`. The auth-login steps remain as an alternative
   section. The corrected cause (30 days from login) replaces the old explanation.
2. `refresh.py` (ConfigMap in `apps/cred-broker/manifests/manifests.yaml`): a helper reads
   `refreshTokenExpiresAt` (epoch ms; only a plausible millisecond number is accepted, anything else
   is ignored so it can never stop a refresh). After a successful refresh, if the refresh token is at
   most `REFRESH_ALERT_DAYS` (7) away, call the existing `alert()` with outcome
   `refresh-token-expiring` and a fixed detail `refresh token expires <ISO date>`; the exit code is
   unchanged. When the refresh is rejected `invalid_grant`, the existing alert gets the same date
   (`expired <date>`) in its detail. The alert body is made generic and points to the doc runbook
   (setup-token default) instead of embedding the old auth-login commands.
3. `apps/cred-broker/application.yaml` lines 13-14: say the refresh token rolls forward but
   its lineage dies about 30 days after the login, so a re-login (or a setup-token) is needed.
4. Tests in `.github/scripts/test_cred_broker.py` in the style of the existing cases.
5. Comment on Factory#3687 with the corrected cause.

## Alternatives rejected

- Suspend the broker under setup-token: it is the 30-day-ahead expiry reminder already.
- Raise the alert on `last-outcome` only: it would not fire while refreshes still succeed.
- Anthropic-side token fixes or an API key: out of scope, subscription only.

## Risks

- A wrong `refreshTokenExpiresAt` unit would alert constantly: ms is confirmed by the live
  value read; a non-number is ignored. Alerts are deduped by the existing marker.
- Alert is best-effort and inert without `GITHUB_TOKEN`.
- Docs say setup-token is inference-only; Remote Control paths are not enabled in gitops.

## Verification

`python3 .github/scripts/extract_embedded_script.py ... /tmp/refresh_extracted.py` then
`python3 .github/scripts/test_cred_broker.py`; YAML parse of the manifests; `kubectl kustomize`
if available; markdown grep for stale "re-seed with `claude auth login`".
