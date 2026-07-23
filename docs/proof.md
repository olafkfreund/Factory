---
layout: default
title: Proof
permalink: /proof/
mermaid: true
---

<style>
.lead{font-size:1.12rem;opacity:.92}
.oneliner{border-left:3px solid #fabd2f;background:rgba(250,189,47,.06);border-radius:0 12px 12px 0;
  padding:1.1rem 1.3rem;margin:1.4rem 0;font-size:1.15rem;line-height:1.5}
.oneliner b{color:#fabd2f}
.kpi{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:12px;margin:1.4rem 0}
.kpi .k{border:1px solid rgba(255,255,255,.12);border-radius:12px;padding:1rem;background:rgba(255,255,255,.02)}
.kpi .k b{display:block;font-size:1.5rem;font-family:'JetBrains Mono',monospace;color:#fabd2f}
.kpi .k span{font-size:.82rem;opacity:.72}
.proof{border-top:1px solid rgba(255,255,255,.08);padding:1.3rem 0}
.proof .tag{font-family:'JetBrains Mono',monospace;font-size:.72rem;letter-spacing:.08em;text-transform:uppercase;color:#83a598}
.proof .see{font-size:.88rem;opacity:.85;margin-top:.6rem}
.cmp{width:100%;border-collapse:collapse;margin:1.3rem 0;font-size:.92rem}
.cmp th,.cmp td{border:1px solid rgba(255,255,255,.12);padding:.6rem .7rem;text-align:left;vertical-align:top}
.cmp th{background:rgba(255,255,255,.04);font-family:'JetBrains Mono',monospace;font-size:.78rem;letter-spacing:.04em}
.cmp td b{color:#8ec07c}
.shots{display:grid;grid-template-columns:repeat(auto-fit,minmax(260px,1fr));gap:14px;margin:1.2rem 0}
.shots img{width:100%;height:auto;border-radius:10px;border:1px solid rgba(255,255,255,.10);box-shadow:0 8px 28px rgba(0,0,0,.35)}
.shots figure{margin:0}
.shots figcaption{font-size:.8rem;opacity:.7;margin-top:.35rem;font-family:'JetBrains Mono',monospace}
.honest{border:1px solid rgba(251,73,52,.35);border-radius:12px;padding:1.1rem 1.3rem;margin:1.4rem 0;background:rgba(251,73,52,.05)}
.honest h3{margin-top:0}
</style>

# Proof, not promises

<p class="lead">Every coding agent claims its output works. This page is about what the
Factory can <strong>prove</strong> — with executed tests, graded verdicts, screenshots,
signed hand-offs and a standing regression suite — and, just as deliberately, about the
things we do <strong>not</strong> claim yet.</p>

## The position

<div class="oneliner" markdown="1">
**The self-hosted governance and verification layer for autonomous coding:** the factory
that runs your agents' code, tests it for real, and refuses to overclaim.
</div>

Four pillars carry that sentence. Everything on this page is evidence for one of them:

1. **Real test execution, not test generation.** Tests are run against the actual
   changed code in a disposable environment — and graded, not just counted.
2. **Verification that structurally cannot overclaim.** The Verification Assurance
   Level (VAL) ladder records what was *actually executed*; the claim is computed from
   the evidence, never typed by a model.
3. **Self-hosted and model-agnostic.** Runs on your cluster, with your models —
   Claude, OpenAI, Gemini, Copilot, Codex or a local Ollama — swapped by configuration.
4. **Separation of duties, signed contracts, humans in the loop.** The service that
   plans is not the service that codes is not the service that verifies; every hand-off
   is an HMAC-signed contract, and approval gates sit where auditors expect them.

We deliberately do not compete on "codes faster." The generation race is crowded and
commoditizing; the empty space in the market is below-left of nobody:

```mermaid
%%{init: {"themeVariables": {
  "quadrant1Fill": "#33360f",
  "quadrant2Fill": "#20242a",
  "quadrant3Fill": "#1d2021",
  "quadrant4Fill": "#241f26",
  "quadrant1TextFill": "#e2e4a0",
  "quadrant2TextFill": "#a89984",
  "quadrant3TextFill": "#a89984",
  "quadrant4TextFill": "#a89984",
  "quadrantPointFill": "#fabd2f",
  "quadrantPointTextFill": "#ebdbb2",
  "quadrantXAxisTextFill": "#ebdbb2",
  "quadrantYAxisTextFill": "#ebdbb2",
  "quadrantTitleFill": "#ebdbb2",
  "quadrantInternalBorderStrokeFill": "#504945",
  "quadrantExternalBorderStrokeFill": "#504945"
}}}%%
quadrantChart
    title Where the agentic coding tools sit
    x-axis Generation-first --> Verification-first
    y-axis Cloud-hosted --> Self-hosted
    quadrant-1 The empty quadrant
    quadrant-2 Open agents
    quadrant-3 Cloud coding agents
    quadrant-4 Cloud QA tools
    Copilot: [0.15, 0.18]
    Jules: [0.24, 0.10]
    Devin: [0.30, 0.14]
    Cursor: [0.22, 0.32]
    Factory.ai: [0.38, 0.20]
    Qodo: [0.62, 0.28]
    OpenHands: [0.32, 0.78]
    Factory - this project: [0.84, 0.86]
```

Devin, Jules, Copilot and Factory.ai generate in someone else's cloud. Cursor generates
in your editor with cloud models. Qodo grades quality but lives in the cloud. OpenHands
self-hosts but is generation-first. **Self-hosted and verification-first is empty — that
is where this project sits.**

The market context says that quadrant is where the pain is:

<div class="kpi">
  <div class="k"><b>84% / 29%</b><span>developers using AI coding tools vs those who trust the output — trust is falling while adoption climbs</span></div>
  <div class="k"><b>81% / 14.4%</b><span>organizations that have deployed AI coding agents vs those whose security teams have approved that use</span></div>
  <div class="k"><b>Aug 2 2026</b><span>EU AI Act high-risk obligations: logging, human oversight and audit evidence become mandatory</span></div>
</div>

For the longer market argument, see [Why Factory](/why/).

---

## What we can prove that others do not

Each item below is a mechanism competitors do not ship, with a pointer to where you can
watch it working — a blog post with screenshots, a demo recording, or the reference spec.

<div class="proof" markdown="1">
<span class="tag">1 · The VAL ladder</span>
### A verdict that names exactly what was executed

Every verified task carries a Verification Assurance Level: **VAL-0** (static analysis
only), **VAL-1** (unit tests executed), **VAL-2** (integration against real but
disposable dependencies — an ephemeral Postgres, a Molecule container, a `terraform plan`),
**VAL-3** (applied against a disposable prod-like target). The achieved level is computed
from the evidence ledger — which commands ran, against which commit, with what output.
If verification is skipped, the result is recorded as VAL-0 at best; it can never be
presented as "tested". A VAL-2 result is rendered so it cannot be mistaken for VAL-3.

Most tools give you a green checkmark. The VAL ladder tells you *which* green checkmark.

<p class="see">See: <a href="/rfc/verification-assurance/">RFC-0006 — Verification Assurance Levels</a> ·
<a href="/blog/2026/06/20/earning-the-right-to-run-unattended/">Earning the right to run unattended</a> ·
<a href="/blog/2026/06/17/seeing-the-proof-test-evidence-in-the-cockpit/">Test evidence in the cockpit</a></p>
</div>

<div class="proof" markdown="1">
<span class="tag">2 · The mutation signal</span>
### Tests graded on whether they would catch a bug

TFactory does not count tests; it grades them on five signals — **coverage delta,
stability across repeated runs, mutation score, lint quality and semantic relevance** to
the acceptance criteria. The mutation signal is the honest one: TFactory injects faults
into the code under test and checks that the generated tests *fail*. A suite that stays
green while the code is deliberately broken is scored down, whatever its coverage number
says. That is the difference between "tests were generated" and "tests would catch a
regression".

<div class="shots" style="grid-template-columns:1fr" markdown="0">
  <figure>
    <img src="/assets/screenshots/tfactory/python-unit.gif" alt="TFactory generating, executing and grading a Python unit-test suite" loading="lazy">
    <figcaption>TFactory generating, executing and grading a test suite on the 5-signal verdict</figcaption>
  </figure>
</div>

<p class="see">See: <a href="/tfactory/">TFactory</a> ·
<a href="/blog/2026/06/12/the-honest-scorecard/">The honest scorecard</a></p>
</div>

<div class="proof" markdown="1">
<span class="tag">3 · MFA-honest UI testing</span>
### Browser tests that log in like a real user — one-time codes included

When acceptance criteria hide behind authentication, TFactory does not mock the login.
It drives a real browser through the real Keycloak flow — username, password, **TOTP
one-time code** — then exercises the UI and records screenshots and screen recordings as
evidence. We proved it on our own product: TFactory logs into all four Factory portals
through MFA and tests every menu and dialog. We also proved it against a deliberately
buggy app deployed to real AWS: the browser test logged in, found the planted validation
fault, and screenshotted it.

<div class="shots" markdown="0">
  <figure>
    <img src="/assets/screenshots/evidence/mfa-otp-challenge.png" alt="TFactory browser test at the Keycloak one-time-code challenge" loading="lazy">
    <figcaption>The browser test at the real TOTP challenge — no mocked auth</figcaption>
  </figure>
  <figure>
    <img src="/assets/demos/webtest/03-invalid-email-ACCEPTED-fault-fail.png" alt="Browser test catching a planted validation fault on a live AWS-deployed form" loading="lazy">
    <figcaption>Catching a planted fault in a live, authenticated app on AWS</figcaption>
  </figure>
</div>

<p class="see">See: <a href="/blog/2026/06/26/tfactory-tests-the-factory/">The test factory tests the factory</a> ·
<a href="/blog/2026/06/18/demoing-the-factory-mfa-plan-to-proof/">One MFA-gated change, from plan to proof</a> ·
<a href="/blog/2026/06/11/testing-authenticated-web-apps/">Logging into a live web app and finding the bug</a></p>
</div>

<div class="proof" markdown="1">
<span class="tag">4 · Signed contracts and separation of duties</span>
### Hand-offs a compliance team can replay

The planner, the coder and the verifier are separate services with separate credentials.
Work moves between them as a **task contract** — a versioned, schema-validated document
whose hand-offs are HMAC-signed and anchored in an audit log, correlated end to end by
one key (the GitHub issue). Nothing reaches a merge without passing the pipeline's
guards: bounded fix loops, human-approval gates, and completion events that record what
was claimed, by whom, with what evidence. The service that wrote the code cannot also be
the service that vouches for it.

<p class="see">See: <a href="/pipeline/">The guarded PARR pipeline</a> ·
<a href="/rfc/task-contract/">RFC-0002 — the task contract</a> ·
<a href="/blog/2026/06/11/the-guarded-parr-pipeline/">The guards behind the pipeline</a></p>
</div>

<div class="proof" markdown="1">
<span class="tag">5 · A standing regression suite</span>
### Verification that keeps running after the task is done

A passing verdict is a statement about one moment. TFactory's continuous-regression
system re-executes accumulated suites on a nightly schedule and on demand — with retry
and quarantine for flaky tests, drift detection when behavior changes under it, and
impact analysis linking failures back to the change that caused them. Verdicts age;
the regression suite is how we notice.

<p class="see">See: <a href="/rfc/regression-suite-and-continuous-verification/">RFC-0018 — regression suite and continuous verification</a> ·
<a href="/tfactory/">TFactory</a></p>
</div>

---

## The factory, tested like a product

The numbers behind the mechanisms, on the codebase itself:

<div class="kpi">
  <div class="k"><b>~2,000</b><span>tests in TFactory alone — the verifier is itself the most-tested service in the fleet</span></div>
  <div class="k"><b>escape corpus</b><span>the OS sandbox that isolates agent code ships with a suite of known escape techniques it must block</span></div>
  <div class="k"><b>byte-exact</b><span>the never-overclaim verdict function is vendored into consumers with a drift guard: CI fails if any copy diverges from the reference</span></div>
</div>

That last one is worth dwelling on: the function that decides what the factory is allowed
to claim is protected against silent modification the same way a checksum protects a
download. Convenient edits to the honesty logic do not survive CI.

## Watch it run

The flagship recording: one brief goes in, and the pipeline plans it, builds it, deploys
it to real cloud infrastructure, verifies it against the live endpoints, and tears it
down.

<div class="shots" style="grid-template-columns:1fr" markdown="0">
  <figure>
    <img src="/assets/demos/parr-deploy-then-verify.gif" alt="Full PARR run: plan, build, deploy to AWS, verify against live endpoints, tear down" loading="lazy">
    <figcaption>Deploy-then-verify on real AWS — the full PARR loop</figcaption>
  </figure>
  <figure>
    <img src="/assets/screenshots/tfactory/polyglot.gif" alt="TFactory verifying tasks across multiple languages" loading="lazy">
    <figcaption>Polyglot verification — the same ladder across languages</figcaption>
  </figure>
</div>

More recorded runs: [deploy-then-verify on AWS](/blog/2026/06/11/deploy-then-verify-on-real-aws/) ·
[a three-tier app on EKS, RDS and ElastiCache](/blog/2026/06/19/three-tier-app-on-aws-with-parr/) ·
[one plan, two clouds](/blog/2026/06/27/one-plan-two-clouds-zero-hands-on-keyboard/) ·
[the portals tour](/tour/) · or download the
[one-page showcase (PDF)](/assets/factory-showcase.pdf).

## What we do not claim

<div class="honest" markdown="1">
### Read this part too

A proof page that hides its limits is marketing. These are ours, today:

- **Most verified tasks top out at VAL-2.** The default ladder climbs as high as is
  achievable locally and ephemerally — real dependencies, but disposable ones. VAL-3
  (applied against a disposable prod-like target) exists in the spec and has run in
  controlled demos, but it is opt-in, gated on credentials and cost guards, and not yet
  the everyday path. When a task says VAL-2, that is what it means — not "tested in
  production-like conditions".
- **The deployment lane is dry-run.** For infrastructure changes the verifier runs
  `tofu init/validate/plan`, policy scanning and image scanning — it does not apply
  infrastructure changes as part of routine verification. Live applies happened only in
  supervised, cost-guarded demo runs.
- **We do not claim to code faster than the benchmark leaders.** The generation race is
  not our race. Our benchmark work is about honest measurement of the whole
  pipeline, not leaderboard placement.
- **This is an early, open project.** No named customers, no revenue claims. What you
  see on this page is what exists: running code, executed tests, recorded evidence.

We think the caps are the credibility. A system whose verifier is structurally unable to
overclaim should describe itself the same way.
</div>

## Sources

Trust and adoption: [Uvik — AI coding assistant statistics](https://uvik.net/blog/ai-coding-assistant-statistics/) ·
[Sonar — State of Code 2026](https://www.sonarsource.com/state-of-code-developer-survey-report.pdf) ·
[DigitalApplied — AI coding adoption statistics 2026](https://www.digitalapplied.com/blog/ai-coding-adoption-statistics-2026-50-data-points).
EU AI Act: [European Commission — regulatory framework for AI](https://digital-strategy.ec.europa.eu/en/policies/regulatory-framework-ai) ·
[artificialintelligenceact.eu](https://artificialintelligenceact.eu/).
Competitor placement reflects each product's published deployment and verification model
as of mid-2026; corrections welcome via
[an issue]({{ site.repo_url }}/issues).

[Why Factory](/why/) · [The pipeline](/pipeline/) · [The tour](/tour/) · [The blog](/blog/)
