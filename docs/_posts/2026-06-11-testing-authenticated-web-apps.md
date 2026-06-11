---
layout: post
title: "Proof: the Factory logs into a live web app, finds the bug, and screenshots it"
subtitle: "We deployed an authenticated web form to real AWS, had a TFactory-style browser test log in as a test user, exercise the UI, catch a deliberate validation fault, and record screenshots as evidence — then tore it all down. If it can do this, it can test and record almost anything."
date: 2026-06-11 14:30:00 +0000
author: Olaf Freund
---

After [deploy-then-verify on real AWS](/blog/2026/06/11/deploy-then-verify-on-real-aws/),
the next question was: can the Factory test something with a **real UI and a
login** — and *prove* what it found? Not an API returning JSON; a web form
behind authentication, tested in a real browser, with screenshots as evidence.

Yes. Here's the proof.

## What we ran

A FastAPI app — a **login page** + a protected **"add contact" form** — deployed
to **AWS App Runner**. The form had a deliberately planted bug: its email
validation was broken, so it accepted `not-an-email` and reported "saved"
instead of rejecting it.

A Playwright browser test (TFactory's own patterns) then:
1. **Logged in as a test user** — `auth.setup.ts` fills the login form from
   injected credentials and saves the session (`storageState`), exactly how
   TFactory authenticates against a target.
2. **Exercised the form** step by step, screenshotting each state.
3. **Caught the fault** — asserted the invalid email is rejected; the bug made
   that assertion fail, and the failing step captured the evidence.

## The recorded evidence

**1 — logged in, the protected form loaded:**

![Logged-in contact form](/assets/demos/webtest/01-app-loaded-pass.png)

**2 — a valid contact saved (the happy path works):**

![Valid contact saved](/assets/demos/webtest/02-valid-contact-saved-pass.png)

**3 — the FAULT: an invalid email was accepted and shown as "saved":**

![Fault: invalid email accepted](/assets/demos/webtest/03-invalid-email-ACCEPTED-fault-fail.png)

That third screenshot *is* the finding — the browser test logged the failure
("invalid email 'not-an-email' was accepted (expected rejection)") and captured
the screen that proves it. Verdict: **fail**, with evidence attached.

## How the login works (the secrets bit)

TFactory keeps test-target credentials out of code. You store a `kind=form`
credential (encrypted at rest) via `POST /api/test-credentials`, then reference
it from `.tfactory.yml`:

```yaml
auth:
  type: ref
  ref: login
  login_url: /login
  username_selector: "#username"
  password_selector: "#password"
  submit_selector: "#login-submit"
  success_url_pattern: "**/app**"
test_credentials:
  login: { ref: env:TEST_PASSWORD, as_username: TEST_USERNAME, as_secret: TEST_PASSWORD, kind: form }
```

The generated `auth.setup.ts` reads those at runtime (never inlined; secrets
redacted from logs), logs in once, and every test reuses the authenticated
session. Findings + screenshots are packaged into a `report.md` + `meta.json` +
`screenshots/` bundle, surfaced via `/api/visual-inspections`.

**Full runbook:** *Testing Authenticated Web Apps* in the
[Factory docs](/architecture/) — what you need, how to add the secret, the
`.tfactory.yml` config, running it, and where the proof lands.

## Cost guard

Real provisioning, real teardown: every resource is tagged `factory-ephemeral`
and named `factory-<spec>-*`; the run's teardown destroyed all of it and left
the account's existing infrastructure untouched. Verified empty after.

## Why it matters

A login form with a planted bug is a stand-in for *any* UI behaviour you care
about — checkout flows, dashboards, multi-step wizards. The Factory deploys it
for real, logs in, drives it, and hands you screenshots of exactly what passed
and what didn't. **Test and record almost anything — with proof.**

*Reusable as the `/run-aws-webtest` command. Real AWS, real browser, real
teardown; the recording/screenshots above are from the actual run.*
