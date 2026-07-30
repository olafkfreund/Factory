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
- Portal-ui lane, what the Evidence tab actually reads:
  `workspaces/portal-ui/specs/<run-id>/findings/screenshots/` and
  `.../findings/videos/` on the control-plane volume. Not `findings/evidence/` —
  that path is the separate per-test evidence tree.
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

Fresh captures (only if recording the AWS webtest variant; the portal variant is
already recorded — see "The recorded portal run" below):
- Beats 1-2 (login screen, credentials entry) if you want them from the current app build.
- Beats 7-8 (proof directory, teardown) as a live terminal recording.
- Full run recording: `asciinema rec -c "bash ~/.claude/skills/run-aws-webtest/conductor.sh"`,
  re-time, then `nix run nixpkgs#asciinema-agg -- out-timed.cast out.gif`.

The existing `docs/assets/demos/webtest/` PNGs are the fault-finding sequence; the
`evidence/` MFA pair covers the login-through-2FA sequence. Between them the whole
story is already on disk.

## The recorded portal run (2026-07-30)

The portal variant of this demo is recorded. A `portal-ui` browser-lane Job logged
into the live TFactory portal through Keycloak with a TOTP code minted at run time,
crawled 14 nav items, and published its evidence to the control-plane volume, where
it renders in the task detail's **Evidence** tab.

- `docs/assets/demos/mfa-browser-test.gif` — the run, terminal side (214 KB).
- `docs/assets/demos/mfa-browser-test.cast` — the raw asciinema recording.
- `docs/assets/screenshots/evidence/mfa-01-keycloak-login.png` — Beat 1/2, the
  Keycloak credential form.
- `docs/assets/screenshots/evidence/mfa-02-otp-challenge.png` — Beat 3, the TOTP
  challenge.
- `docs/assets/screenshots/evidence/mfa-03-authenticated-pipeline.png` — Beat 5,
  the authenticated pipeline board with this run in the Report lane.
- `docs/assets/screenshots/evidence/mfa-04-evidence-tab.png` — Beat 7, the Evidence
  tab showing `Recordings (1)` and `Screenshots (16)`.

![MFA browser test: the Job takes credential references not values, logs in through a TOTP challenge, and lands screenshots plus a screencast on the control-plane volume](/assets/demos/mfa-browser-test.gif)

The Evidence tab for that run, reached by clicking the task card:

![The TFactory task detail Evidence tab for run mfa-demo-243, showing one recording and sixteen screenshots beginning with the Keycloak login and the TOTP challenge](/assets/screenshots/evidence/mfa-04-evidence-tab.png)

The run reported `MFA presented: True, logged in: True` and the Job exited
`succeeded=1`. Verdict was `attention`, from three console errors on the portal
(a 401, a blocked Google Fonts stylesheet, a cross-portal fetch) — not from the
login, which passed.

Two things to state plainly when showing this:

- The two auth screenshots are captured **before any value is typed**, so no
  username, password or one-time code is in them. The username the OTP page echoes
  back is a value from the `portal-ui-test-user` Secret and is masked in the
  committed copies; the unmasked originals stay on the control-plane volume behind
  the portal's own login.
- The task detail has **no URL**. `TFactoryPortal` is state-driven, so the Evidence
  tab is reached by clicking the task card, not by navigating to a link
  (TFactory#878).

Reproduce it with:

```sh
# credentials come from the Secret via env; never on a command line
kubectl --context factory -n factory apply -f <portal-ui job manifest>
kubectl --context factory -n factory logs -f job/portal-ui-tfactory-<run-id>
nix run nixpkgs#asciinema-agg -- --idle-time-limit 1 out.cast out.gif
```

### What recording it found

Recording this demo surfaced three faults in the browser lane itself, all fixed in
TFactory and each one invisible in the verdict:

- The Job's pod carried `app: tfactory`, the portal Service's own selector, so it
  joined the Service, served connection-refused for its share of real traffic, and
  took the portal offline for the duration of the test (TFactory#877 sibling fix).
- `ensure_logged_in` reported `logged in: True` when it had never reached a login
  form, so a portal serving a Cloudflare 502 graded `attention` instead of `fail`
  (TFactory#877).
- The screencast was recorded and then discarded, so the Evidence tab's Recordings
  section was always empty (TFactory#876).

That is the demo's real argument: the evidence caught what the green verdict did not.

## Proof takeaway

This is real UI testing behind a real MFA login, on a real cloud deployment, with
dated screenshot evidence of both a passing path and a caught fault. The agent did
not mock the auth, skip the second factor, or assert green on faith. It logged in
like a person, tested like a tester, and left proof a skeptic can open.
