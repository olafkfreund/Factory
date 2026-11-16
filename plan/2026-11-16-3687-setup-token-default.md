---
status: draft
issue: 3687
spec: spec/2026-11-16-3687-setup-token-default.md
coders:
  1: lead   # tricky logic in one script block plus its tests; a handoff costs more than it saves
  2: lead   # prose edit tied to step 1's wording
  3: lead   # one comment edit
reviewers:
  - codex   # final diff review
  - agy     # final diff review
---

# Plan: setup-token as the default Claude credential flow

Repo for all edits: olafkfreund/factory-gitops, branch `fix/3687-setup-token-default` off
`origin/main`. Approved decisions (spec): setup-token is the documented default, auth login the
alternative (~30-day re-login); the broker reads `refreshTokenExpiresAt` (epoch ms) on a
refreshable credential and uses the existing `alert()` when it is within 7 days or past (outcome
`refresh-token-expiring`, fixed detail carrying the ISO date), then refreshes as before with the
exit code unchanged; the alert body wording becomes generic with setup-token first; the
`application.yaml` comment is corrected. Do not touch live Secrets, RBAC or the cluster.

## Steps

1. `apps/cred-broker/manifests/manifests.yaml`, `refresh.py` block (lines ~85-410) and
   `.github/scripts/test_cred_broker.py` (lines ~96-180). Add `REFRESH_ALERT_DAYS = 7` next to
   `LONG_LIVED_DAYS` and a helper `refresh_expiry(oauth)`: reads `refreshTokenExpiresAt`; accepts only a
   non-bool int/float with `1e12 <= v < 1e14` (epoch ms; anything else, including 0, negatives, seconds,
   inf, is ignored, so metadata can never stop a refresh); returns `(days_left, note)` with note
   `refresh token expires <ISO>` or `refresh token expired <ISO>`, or `None`. Use it in two places:
   (a) after the successful refresh and patch, if `days_left <= 7`: `alert("refresh-token-expiring", note,
   oauth["expiresAt"])`, and `record("ok", f"access TTL ..; {note}", ...)` so the annotation carries the date
   too; exit stays 0. (b) in the `invalid_grant` branch (past the >30d exemption), append the note to
   the alert detail so an already-dead lineage shows its date; no extra alert call, so no double alert.
   `alert()` body: first line "needs a human re-seed" (not "could not be refreshed"); replace the
   embedded kubectl re-seed steps (old steps 1-3, 5) with a pointer to `docs/secrets-management.md`
   "Re-seeding the Claude OAuth credential" (default: `claude setup-token`; alternative: `claude auth
   login`), keep the fresh-name verify block and say expect `not-applicable:long-lived-credential`
   (setup-token) or `ok` (auth login); say `refresh-token-expiring` is a warning raised while refreshes
   still succeed and does not clear until re-seeded, and that the existing issue is not updated when the
   credential later dies. Fix the two stale comments in `main()` that say to re-seed with `claude auth
   login` ("the refresh token was consumed elsewhere..." and the `NOTE` about retiring the broker).
   Tests: `arun()` gets `rexp_days` (None omits the field; or a raw value) and a granted-refresh mode;
   the GitHub fake becomes stateful (a POSTed issue appears in later GETs). Cases: 6d alerts (SEND, rc
   0, body has the ISO date and `refresh-token-expiring`, checked by exact string, not substring of
   `ok`); 8d quiet; absent, `"x"`, `True`, `0`, `-1e30`, `float("inf")`, seconds-scale value: quiet and
   refresh still patched; no GITHUB_TOKEN inert; open issue dedupes; past + `invalid_grant`: exactly one
   issue across the run, date in body; two consecutive runs: one issue. Check: extract the script and
   run `python3 .github/scripts/test_cred_broker.py`.
   Traps: indentation inside the YAML block scalar is 4 spaces; stdlib only; never print tokens or
   provider bodies; `alert()` gets fixed strings only; `iso()` never called with None; CI extracts via
   `.github/scripts/extract_embedded_script.py`.
2. `docs/secrets-management.md`: the "Only one secret rotates automatically" line (~37), ~76, ~182, the
   Inventory row for `factory-cli-creds` (~51), the rotation policy row (~207), and the section
   "Re-seeding the Claude OAuth credential" (starts ~295, flow table ~325). Table lists `setup-token`
   (default, about 1 year, no refresh token, broker reports `not-applicable:long-lived-credential` and
   stays on as the 30-day expiry reminder via `no-refresh-token`) and `auth login` (alternative: the
   refresh lineage dies about 30 days after the login, rotation does not extend it,
   `refreshTokenExpiresAt` is in the file, the broker alerts 7 days ahead). Default procedure: optional
   read of the dead file's expiry date only; `claude setup-token`; `read -rs TOK`; patch
   `factory-cli-creds` with `{"claudeAiOauth":{"accessToken":TOK,"expiresAt":<epoch ms, 360 days out>,
   "scopes":["user:inference"]}}`; patch `factory-secrets` `CLAUDE_CODE_OAUTH_TOKEN`; update the agenix
   slots (`factory-secret-factory-secrets`, and refresh `factory-cli-creds`) so a reboot keeps it; a
   fresh verify Job expecting `not-applicable:long-lived-credential`; announce on the agent bus, then
   roll the consumers (cred-sync refuses a seed more than 90 days fresher than the file in the pod;
   a fresh pod seeds directly); TFactory health check (`validity: valid`). Keep the auth-login steps as
   "Alternative" (re-login about every 30 days; expect `ok`; the workstation-sharing warning applies
   to it). Fix the "no re-login" statements, add the confirmed cause. Check: grep shows no remaining
   "re-seed, use `claude auth login`" default; run `scripts/rotation-ledger-check.py` if it exists.
   Traps: never show a secret value; keep `--context k3d-factory`; fenced blocks stay shell-valid.
3. `apps/cred-broker/application.yaml` lines 13-21: the refresh token rolls forward but its lineage
   expires about 30 days after the interactive login, so re-login (or setup-token) is needed; the
   broker alerts 7 days ahead. Also fix the `manifests.yaml` comment at `LONG_LIVED_DAYS` if it says
   the same. Check: the YAML still parses.
4. Comment on olafkfreund/Factory#3687 (lead, after the PR is open): about 30 days from login, not about
   14 from the Secret's creation; three of five incidents were cluster rebuilds or outages; link the PR.

## Tests

`python3 .github/scripts/extract_embedded_script.py apps/cred-broker/manifests/manifests.yaml refresh.py /tmp/refresh_extracted.py && python3 .github/scripts/test_cred_broker.py`
prints "both directions correct"; `python3 .github/scripts/test_cred_sync.py` is unaffected; repo CI
checks are green on the PR head.

## Rollback

Revert the PR; the broker returns to the #340 behaviour. No cluster state is touched.
