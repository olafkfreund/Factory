---
layout: post
title: "The test factory tests the factory: TFactory now drives the Factory portals through MFA"
subtitle: "Real Keycloak logins, every menu and dialog exercised, screenshots and verdicts surfaced where humans already look"
date: 2026-06-26
author: Olaf Freund
---

For a while there was an awkward gap in the Factory suite. **TFactory** could generate and
run tests for the code the fleet produced, but it could not test the thing we look at every
day: the **portals themselves**. The plan board, the task board, the test pipeline, the
cockpit — all four are real web applications behind Keycloak, and none of them had an
automated way to prove they still rendered, navigated, and behaved after a deploy.

That gap is now closed. TFactory has a new capability that drives a deployed portal the way a
person would: it logs in through **Keycloak with a real time-based one-time code**, walks
every navigation item, dropdown, and dialog, captures a screenshot of each, records a
screencast of the whole run, and writes a verdict report. It runs against all four portals,
and the results land in the same places the team already reviews evidence.

This post is the honest version of how it got there, including the parts that did not work
the first time.

## What it actually does

The capability is a small, portal-agnostic harness. Given a portal URL it:

1. Opens the portal in a real headless Chromium with a normal browser user-agent (the portals
   sit behind Cloudflare, which rejects non-browser clients).
2. Drives the login: the portal's own sign-in page, then **Sign in with SSO**, then the
   Keycloak username and password form, then the one-time-code challenge. The code is minted
   from the test user's enrolled secret, so the second factor is genuinely computed — never
   stubbed or bypassed.
3. Crawls the live DOM rather than a hard-coded map: it discovers the navigation, clicks each
   item, opens each dropdown, opens and cancels each dialog (never committing a destructive
   action), and screenshots every step.
4. Writes a report with an honest verdict and per-control counts, plus the screenshots and a
   screencast as evidence.

Here are the four portals, each captured by the harness after a real MFA login.

![PFactory, the planning portal, after an automated MFA login]({{ '/assets/screenshots/portal-ui/pfactory-portal.png' | relative_url }})

![AIFactory, the code portal, after an automated MFA login]({{ '/assets/screenshots/portal-ui/aifactory-portal.png' | relative_url }})

![TFactory, the test portal, after an automated MFA login]({{ '/assets/screenshots/portal-ui/tfactory-portal.png' | relative_url }})

![CFactory, the cockpit, after an automated MFA login]({{ '/assets/screenshots/portal-ui/cfactory-portal.png' | relative_url }})

## Where it runs, and why that matters

The control-plane pod has no browser, so each portal test runs as a **Kubernetes Job** on a
dedicated runner image (Microsoft's Playwright base, with the browsers baked in). The MFA
credentials come from a Secret as environment variables — never on a command line. The Job
co-mounts the same data volume the control plane uses, so when it finishes, its findings show
up exactly where humans already look:

- the **Visual Reports** tab, with the report and the screenshot gallery;
- the **TFactory Pipeline** in its Report lane, as a finished test;
- the **CFactory cockpit**, as a finished work item.

No new screen to learn. The portal test is just another test result.

## It finds real problems

A test harness is only worth having if it catches things, and this one already has. While
crawling AIFactory it opened the Delete-task dialog and the confirmation came back with
`Missing Authorization header`. That was a genuine bug: the frontend was not sending the
single-sign-on session cookie on mutating requests, so delete (and other actions) failed for
SSO-only sessions. It is fixed. The harness surfaced it simply by clicking the button a person
would click.

The crawler also handles the messy reality of real portals. PFactory greets a fresh login with
a "Git Repository Required" modal whose backdrop swallows every click. The harness recognises a
blocking modal, dismisses it with a non-committing action, and carries on — then records that
it did so.

![The harness dismissing PFactory's onboarding modal before crawling]({{ '/assets/screenshots/portal-ui/pfactory-modal.png' | relative_url }})

## The parts that did not work first time

Three failures were worth the trip.

**Time-based codes are one-time.** Running all four portals at once, two logins kept failing
with "Invalid authenticator code." The cause was not clock skew; it was that the same test user
reused the same 30-second code across concurrent logins, and Keycloak correctly rejects a
replayed code. The fix is built into the dispatch now: each portal's Job staggers its login so
they land in different time windows. With the stagger, the most recent run logged in to all
four on the first attempt.

**A starved browser misses clicks.** In-cluster, navigation clicks that passed locally timed
out. The Job had no CPU request, so the browser was throttled and the click actionability checks
expired. Giving the Job a real CPU and memory request — plus a more patient click that scrolls
into view and falls back to a forced click — took a portal from three captured controls to
fifteen.

**A report is not a verdict.** The first cards read "0 pass, 0 fail," because the counts were
derived from screenshots and every benign console message was treated as a failure. Now a
"failure" is a failed interaction; an expected console message nudges the verdict to "needs
attention," not "fail"; and a run only fails outright if it could not log in or a majority of
controls broke. The cards now say something true.

## What this unlocks

This is the milestone: **the test factory can now test the factory.** From here on, TFactory is
how we verify Factory's own features. A portal change is not done when it merges; it is done
when TFactory has logged in, walked it, and shown the screenshots.

There is a neat symmetry to it. We built a system to plan, code, and test software, and the most
demanding software it now tests is itself. The best way to trust a tool is to use it on the work
that matters most — and nothing matters more to us than the Factory holding together. So we point
it inward. We get better at building the tool by using the tool.

The capability lives in TFactory as the `portal-ui` framework, runs on a published runner image,
and ships with one test plan per portal and a flow that turns findings into GitHub issues. It is
proven, it is on by default for our own portals, and it has already paid for itself by finding a
real bug on day one.
