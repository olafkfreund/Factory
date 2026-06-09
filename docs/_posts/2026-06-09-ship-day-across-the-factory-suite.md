---
layout: post
title: "Ship day: the Hermes learnings land — and a lot more"
subtitle: "In a single day the four-product suite shipped agent-loop hardening, CI-parity verification, per-user API keys, an Ollama Cloud provider in every product, and a cockpit that finally tells the truth. A grounded changelog — with what's on main and what's still on dev."
date: 2026-06-09
author: Olaf Freund
---

This morning we [closed out the Hermes adoption tickets](/blog/2026/06/09/what-the-hermes-agent-taught-us/)
and parked the one open research idea as [RFC-0004](/rfc/trajectory-capture/). By
this evening, the code those tickets described was merged and tagged across the
suite — alongside a surprising amount of other work. Four products moved at once.

This is the honest changelog. We've split it by *theme* rather than by product,
because the interesting story today is how the same idea showed up in three or four
places at once. At the end there's a flat per-product list if you just want the
receipts. Where something landed on `main` (released) versus `dev` (in flight), we
say so — no pretending a branch is a release.

## 1. The Hermes learnings stopped being a blog post and became code

We wrote up [what we learned reading Nous Research's Hermes agent](/blog/2026/06/09/what-the-hermes-agent-taught-us/)
this morning. Two of those learnings shipped to `main` the same day.

**AIFactory v3.6.0 — act-loop hardening.** Three small, independently env-gated
modules now wire into the Claude Agent SDK's `PreToolUse` / `PostToolUse` /
`PreCompact` hook points ([#477](https://github.com/olafkfreund/AIFactory/pull/477),
closing #474 #475 #476):

- **Anti-loop / no-progress guardrail** (`agents/guardrails.py`). Detects repeated
  exact failures, the same tool failing N times, and idempotent reads that keep
  returning the same thing — then blocks the offending call or halts the turn with a
  typed `halt_reason`. That reason rides into the
  [RFC-0001](/rfc/correlation-key/) completion event, so CFactory can show you *why*
  a work item stalled instead of just that it did.
- **Budgeted context summary** (`agents/context_summary.py`). At the compaction
  boundary it builds a deterministic, token-budgeted summary of the active task and
  persists it to `active_context.md` for re-injection after the window is compacted.
- **Checkpoint-before-mutation + mutation ledger** (`agents/mutation_ledger.py`).
  Before a mutating tool runs, a cheap git checkpoint is taken; every mutation is
  recorded to `.aifactory/mutations.jsonl`; a turn-end `verify_turn()` flags
  claimed-vs-actual mismatches, and `rollback_to()` can restore a checkpoint.

Every one of these is **off unless you opt in** (`AIFACTORY_GUARDRAIL_*`,
`AIFACTORY_CONTEXT_SUMMARY`, `AIFACTORY_MUTATION_LEDGER`). Nothing changes for
existing runs until you ask for it.

**TFactory v0.8.0 — CI-parity verification.** TFactory grades work on a multi-signal
verdict; today it gained a new signal aimed squarely at *green that lies*
([#302](https://github.com/olafkfreund/TFactory/pull/303)). Two parts: it runs the
graded tests in a **CI-matched environment** (credentials blanked, `TZ=UTC`,
`PYTHONHASHSEED=0`, `--network=none --read-only`), and it does a static scan
(`agents/ci_parity.py`) that flags tests which pass only because they **mock out the
very module under test**. The result surfaces as `signals_summary.ci_parity`
(`yes` / `mocked-subject` / `no`). It's default-on; set `TFACTORY_CI_PARITY=0` to
disable.

That's the loop we said we wanted this morning: read someone's open-source code,
take the good parts, ship them — verified, gated, and threaded into our own
contracts.

## 2. The Act → Reflect handoff got tighter

AIFactory can now **auto-hand a finished task to TFactory** for test generation the
moment a build completes ([#496](https://github.com/olafkfreund/AIFactory/pull/501)
backend, [#503](https://github.com/olafkfreund/AIFactory/pull/505) UI toggle). It's
per-task and opt-in — a checkbox in the task wizard sets `auto_handover_tfactory`,
and on a `COMPLETED` build AIFactory hands the spec and changes to TFactory
best-effort (it never blocks or breaks task completion, and it's a no-op if
`TFACTORY_BASE_URL` is unset).

The nice part: the handoff payload now **embeds the mutation ledger** from §1, so
TFactory receives exactly what the coder changed as evidence — not a guess
reconstructed from the diff. The two Hermes-inspired features compose.

## 3. One auth story across the suite: per-user `acw_` keys

Until today, programmatic REST access leaned on a shared `APP_API_TOKEN`. Now
**AIFactory** ([#479](https://github.com/olafkfreund/AIFactory/pull/499)),
**PFactory** ([#93](https://github.com/olafkfreund/PFactory/pull/95)) and
**TFactory** ([#305](https://github.com/olafkfreund/TFactory/pull/307)) all accept
**per-user, scoped `acw_` API keys** minted in their Settings UIs, resolved by the
same shared auth path. Expired and revoked keys are rejected, `last_used_at` is
stamped, and scopes are enforced (an `mcp:read`-only key can't call the full REST
surface). The `/handover` flow and CLI clients can stop sharing one admin token.

It's a small thing that matters a lot operationally: three products, one consistent
credential model, all landed the same day.

## 4. One provider story: Ollama Cloud, everywhere

All four products gained an **Ollama Cloud** option today, each routed through the
existing OpenAI-compatible backend (so it's config, not a new provider class):

- **AIFactory** & **PFactory** ([#94](https://github.com/olafkfreund/PFactory/pull/95))
  — `ollama-cloud` as a first-class provider/alias, authed by `OLLAMA_API_KEY`,
  endpoint `https://ollama.com/v1`, kept deliberately separate from local `ollama`.
- **TFactory** ([#306](https://github.com/olafkfreund/TFactory/pull/308)) — verified
  via `providers/ollama_cloud_check.py` plus an operator guide.
- **CFactory** ([#62](https://github.com/olafkfreund/CFactory/pull/62)) — the
  cockpit *copilot* can now run on Ollama Cloud instead of Claude, selectable at
  runtime (more on that below).

This is the [why.md](/why/) thesis in practice — *"a new model or agent is a small
adapter, not a rewrite."* A hosted-inference option dropped into four codebases by
configuration.

## 5. A sandbox that actually sandboxes

A genuinely important fix: the hardened Chainguard runtime image was **missing
`bubblewrap` and `socat`**, so the Claude Agent SDK quietly logged "Sandbox
disabled" and ran agent bash commands with **no filesystem or network isolation**.
Both packages are now installed so the sandbox actually engages
([AIFactory #363](https://github.com/olafkfreund/AIFactory/pull/509);
the same fix is in flight for PFactory [#98](https://github.com/olafkfreund/PFactory/pull/98)
and TFactory [#321](https://github.com/olafkfreund/TFactory/pull/321)). If you run
these in production, this is the one to pull.

A few more AIFactory robustness fixes shipped in the same train (v3.6.2–v3.6.5):
headless runs no longer hang on an interactive prompt, default-org seeding is
idempotent, the worktree merge stashes a dirty base tree before merging
([#485](https://github.com/olafkfreund/AIFactory/pull/497)), and spec phases now
**surface a provider auth failure immediately** instead of silently retrying until
the real cause is buried ([#483](https://github.com/olafkfreund/AIFactory/pull/498)).
Multi-layer features also stop collapsing into "Quick Flow": a structural-complexity
floor ([#504](https://github.com/olafkfreund/AIFactory/pull/506)) raises (never
lowers) the plan tier when it sees multiple endpoints, layers and deliverables.

## 6. CFactory grew a conscience

The cockpit — the [control tower](/architecture/) that watches the whole PARR
pipeline — spent the day learning to tell the truth instead of showing a green light
over a broken connection:

- **Honest upstream status** ([#60](https://github.com/olafkfreund/CFactory/pull/60),
  [#61](https://github.com/olafkfreund/CFactory/pull/61)). The adapters now send
  `Authorization: Bearer` to the upstream factories (they were getting silent 401s),
  and the Services view distinguishes **online** (200) / **auth error** (401-403,
  amber) / **offline** / **error** instead of calling anything that answers "online".
- **No more ghost tasks** ([#66](https://github.com/olafkfreund/CFactory/pull/66)).
  When AIFactory drops a task from its list (a restart, a different run), CFactory
  used to keep showing it as "in_progress" forever. A new
  `store.reconcile_snapshot()` blanks non-terminal stages the upstream no longer
  reports — terminal and completion-event-sourced items are preserved — so the board
  stops showing work that isn't running.
- **Only live agents** ([#65](https://github.com/olafkfreund/CFactory/pull/65)). The
  live-agents panel now excludes review/queued/terminal tasks, auto-refreshes, and a
  closed stream reads "agent finished" instead of a confusing "stream ended".
- **A pluggable copilot with a Settings view**
  ([#64](https://github.com/olafkfreund/CFactory/pull/64),
  [#63](https://github.com/olafkfreund/CFactory/pull/63)). You can now switch the
  cockpit copilot between Claude and Ollama Cloud at runtime — with live model
  discovery and a connectivity check — without a redeploy. The API key is never
  persisted (env/secret only), and answers finally render as markdown.

Underpinning all of it, CFactory's completion-event store now **dedupes on the
envelope `id`** ([#57](https://github.com/olafkfreund/CFactory/pull/57)) rather than
the old `(service, key, status)` tuple — so the outbox relay re-delivering an event
is a no-op, while a legitimate re-run after handback still threads in with a fresh
`id`. That's the [RFC-0001](/rfc/correlation-key/) envelope doing exactly what it
was designed to do.

## 7. TFactory's enterprise wedge (on `dev`, rolling out)

Separately from v0.8.0, a large stream of enterprise-facing work landed on
TFactory's `dev` branch today. It's **not on `main` yet** — it's verifying behind
the portal — but it's worth flagging because it's where TFactory is heading:

- **A PR-native quality gate** ([#310](https://github.com/olafkfreund/TFactory/pull/310)–[#312](https://github.com/olafkfreund/TFactory/pull/312))
  — a pure-compute gate that turns the verdict set into a GitHub commit status
  (`TFactory / tests`) with policy in `.tfactory.yml`. Opt-in, dry-run by default.
- **A no-AIFactory spec front door** ([#313](https://github.com/olafkfreund/TFactory/pull/313)–[#315](https://github.com/olafkfreund/TFactory/pull/315))
  — `POST /api/specs/ingest` lets you hand TFactory a markdown/Gherkin/EARS spec
  directly, so it can verify code it didn't build, decoupling it from AIFactory.
- **Multi-tenant `ProjectStore`** ([#316](https://github.com/olafkfreund/TFactory/pull/316)–[#319](https://github.com/olafkfreund/TFactory/pull/319))
  — an org-scoped persistence seam (JSON default, DB backend behind
  `APP_PROJECTS_BACKEND`) plus a legacy-`projects.json` → DB migration. Additive and
  reversible; no cutover yet.
- **Java coverage** ([#320](https://github.com/olafkfreund/TFactory/pull/320)) — a
  format-aware coverage signal that parses JaCoCo, so the verdict works for JVM
  projects, not just Cobertura/Python.

## The receipts — per product

| Product | Released on `main` today | Notable |
|---|---|---|
| **AIFactory** | v3.6.0 → **v3.6.8** | Act-loop hardening (#474/475/476/477); TFactory auto-handover + UI toggle (#496/#503); per-user `acw_` keys (#479); spec auth-error surfacing (#483); worktree merge stash (#485); complexity floor (#504); **sandbox bubblewrap+socat** (#363); stdio-MCP handover fixes (#494) |
| **PFactory** | **v0.6.4** + GitHub Agentic epic #87 (#91/#92) | Per-user `acw_` tokens (#93); Ollama Cloud (#94); GitHub Models provider + Copilot cloud-agent dispatch + planning-context MCP server + Actions workflows; amd64-only release CI (#97). *In flight: unified Planning board, sandbox deps (#98).* |
| **TFactory** | **v0.8.0** | CI-parity verification signal (#302); `acw_` keys (#305); Ollama Cloud (#306). *On `dev`: PR quality gate (#310-312), spec ingest front door (#313-315), multi-tenant ProjectStore (#316-319), JaCoCo coverage (#320), sandbox deps (#321).* |
| **CFactory** | (rolling release) | Event dedup on envelope id (#57); upstream auth + honest status (#60/#61); no ghost tasks (#66); live-agents-only (#65); pluggable copilot + Settings + Ollama Cloud (#59/#62/#63/#64) |

## What ties it together

Read the themes back and a pattern falls out. Today wasn't four products doing four
unrelated things — it was the **suite converging**: the same auth model, the same
provider option, the same sandbox fix, the same Hermes-derived discipline, all
landing in parallel and all threaded by the [same correlation key and
contracts](/rfc/correlation-key/) we've been building toward. The handoff from
AIFactory's mutation ledger straight into TFactory's verdict is the clearest example
— two features, two repos, one day, composing into something neither could do alone.

That's the bet [Factory](/why/) is making: code generation commoditizes, but a
*governed, verified, observable* pipeline around it compounds. Days like this are
what compounding looks like.

*Everything above is grounded in merged commits; where work is still on `dev` or a
feature branch we've said so. Building in the open means you can check our
work — the PRs are all linked.*
