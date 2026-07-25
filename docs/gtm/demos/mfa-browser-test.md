# Demo runbook: MFA browser test with screenshot evidence

## The point

A buyer who suspects "your agent can't even get past a login" watches the Factory
log in as a real test user through a one-time-code MFA challenge, drive the
authenticated UI, catch a fault the app should have rejected, and drop dated
screenshots as proof. No mock, no stubbed auth. Real login, real fault, real evidence.

## What this proves

- TFactory logs in through MFA (Playwright, TFactory storageState pattern), not around it.
- It exercises a UI that only exists behind that login.
- It finds a real fault (a validation bug the app wrongly accepts).
- It records screenshots as durable evidence, tied to the run.

## Setup and preconditions

Target app: the bundled authenticated web app from the `run-aws-webtest` capability.
It is a FastAPI login plus a protected contact form deployed to real AWS App Runner
(proven 2026-06-11, acct 533267307120 / eu-west-2). The form carries a deliberate
email-validation fault so the browser test has something real to catch. The whole
stack is `factory-ephemeral` tagged and torn down on exit (cost-guarded, a few cents).

Alternative target: one of the live Factory portals behind its MFA login, using the
same portal-UI / MFA Playwright harness. Use the AWS webtest app when you want a
clean fault to catch on demand; use a portal when you want to show it against the
product's own authenticated surface.

MFA / test-user setup:
- Credentials come from env at run time, never hard-coded (`kind=form` credential
  pattern; stored encrypted via `POST /api/test-credentials` when driven through a
  deployed TFactory).
- The login is a real MFA flow: username/password then a one-time-code (OTP)
  challenge. The test completes the challenge and persists a Playwright
  `storageState`, so the authenticated session carries into the UI test.
- Reference: `AIFactory/guides/testing-authenticated-web-apps.md` (credential
  storage, `.tfactory.yml` `auth: {type: ref}`, generated `auth.setup.ts`, where
  screenshots and findings land).

Prereqs to run live: `terraform`, `docker` (daemon up), `aws` CLI, `python3`, AWS
creds at `ENVRC`. One command: `bash ~/.claude/skills/run-aws-webtest/conductor.sh`
(~8-10 min; App Runner provisioning is the slow part).

## Step-by-step shot list

Beat 1 — The locked door.
Shot: the login screen of the target app.
Narration: "This UI does not exist without a login, and the login demands a second
factor. This is where 'can your agent even log in?' gets answered."

Beat 2 — Username and password.
Shot: credentials entered (values masked; they come from env, never the transcript).
Narration: "The test user's credentials are injected from encrypted storage at run
time. Nothing secret is ever printed."

Beat 3 — The MFA challenge.
Shot: the one-time-code (OTP) prompt.
Reuse: `docs/assets/screenshots/evidence/mfa-otp-challenge.png`.
Narration: "The pipeline stops at the same 2FA wall a human would. It does not
skip it, it answers it."

Beat 4 — Authenticated.
Shot: the post-login authenticated view.
Reuse: `docs/assets/screenshots/evidence/mfa-authenticated-account.png`.
Narration: "`authenticate: passed`. The session is real and persisted as Playwright
storageState, so every later step runs as a logged-in user."

Beat 5 — Drive the UI, happy path.
Shot: a valid contact saved successfully.
Reuse: `docs/assets/demos/webtest/02-valid-contact-saved-pass.png`
(and `01-app-loaded-pass.png` for the loaded form).
Narration: "First it proves the good path works. A valid submission is accepted and
saved."

Beat 6 — Find the fault.
Shot: an invalid email that the app wrongly accepts.
Reuse: `docs/assets/demos/webtest/03-invalid-email-ACCEPTED-fault-fail.png`.
Narration: "Now the real job. The test submits a malformed email. The app accepts
it. That is a fault, and the browser test flags it, filename and all:
`invalid-email-ACCEPTED-fault-fail`."

Beat 7 — Evidence lands.
Shot: the collected proof directory / findings.
Narration: "Every step wrote a screenshot to `proof/screenshots/`, and the fault
is recorded in `results.json`. Behind a deployed TFactory these land as visual
inspections (`/api/visual-inspections`, with `report.md` / `meta.json`)."

Beat 8 — Clean up.
Shot: teardown confirmation.
Narration: "The stack was ephemeral. `terraform destroy` runs on exit, even on
failure. All that remains is the evidence."

Where evidence lands:
- Live run: `/tmp/webform-demo/proof/screenshots/*.png` and `results.json`.
- Through a deployed TFactory: `/api/visual-inspections` (`report.md`, `meta.json`).
- Committed demo assets: `docs/assets/screenshots/evidence/` (MFA login/OTP) and
  `docs/assets/demos/webtest/` (form pass/fault).

## Existing assets to reuse vs fresh captures

Reuse (already committed, no rerun needed):
- `docs/assets/screenshots/evidence/mfa-otp-challenge.png` — the OTP challenge (Beat 3).
- `docs/assets/screenshots/evidence/mfa-authenticated-account.png` — logged in (Beat 4).
- `docs/assets/demos/webtest/01-app-loaded-pass.png` — form loaded (Beat 5).
- `docs/assets/demos/webtest/02-valid-contact-saved-pass.png` — happy path (Beat 5).
- `docs/assets/demos/webtest/03-invalid-email-ACCEPTED-fault-fail.png` — the fault (Beat 6).
- `docs/assets/screenshots/portal-ui/tfactory-portal.png` — optional portal context shot.

Fresh captures (only if recording a new screencast):
- Beats 1-2 (login screen, credentials entry) if you want them from the current app build.
- Beats 7-8 (proof directory, teardown) as a live terminal recording.
- Full run recording: `asciinema rec -c "bash ~/.claude/skills/run-aws-webtest/conductor.sh"`,
  re-time, then `nix run nixpkgs#asciinema-agg -- out-timed.cast out.gif`.

The existing `docs/assets/demos/webtest/` PNGs are the fault-finding sequence; the
`evidence/` MFA pair covers the login-through-2FA sequence. Between them the whole
story is already on disk. Recording is a follow-up; this runbook plus these assets
is enough to give the demo today.

## Proof takeaway

This is real UI testing behind a real MFA login, on a real cloud deployment, with
dated screenshot evidence of both a passing path and a caught fault. The agent did
not mock the auth, skip the second factor, or assert green on faith. It logged in
like a person, tested like a tester, and left proof a skeptic can open.
