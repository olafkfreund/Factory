---
layout: default
title: Roadmap
permalink: /roadmap/
---

# Program roadmap

Factory is managed as one program across five repositories, tracked on the
[Factory Program board](https://github.com/users/olafkfreund/projects/1). The
sequencing principle is **spine first**: make the pipeline traceable end-to-end
before building deep on top of it.

## Recently shipped (June 2026)

The PARR spine is now proven end-to-end on real infrastructure:

- **In-cluster ephemeral verification** — the verification ladder
  ([RFC-0006](rfc/0006-verification-assurance-levels.md)) now runs on the shared
  `factory-sandbox` primitive ([RFC-0005](rfc/0005-environment-manifest-and-toolchain-provisioning.md)),
  with a reference stack landed in the hub (`scripts/verification_{profiles,gate,runner}.py`,
  `scripts/factory_sandbox.py`). AIFactory — whose pod has no container runtime —
  runs each trailing gate as an ephemeral **Kubernetes Job** under a least-privilege
  `aifactory-sandbox` ServiceAccount, **co-mounting the task worktree** so
  lint/test/build gates run against real files. Proven live: a gate Job ran
  `go test -v ./...` green against a real worktree, result flowing through the
  never-overclaim gate. Opt-in/default-off; honest caveats (one toolchain image
  per Job, synthetic exit code, single-node co-mount) are tracked in RFC-0005 §3.3.
- **Access discovery for authenticated testing (design)** — a new
  [RFC-0007](rfc/0007-access-and-credential-provisioning.md) (proposed; epic with
  sub-issues filed) tackles the MFA/credentialed-target question: classify each
  test target into four access classes (machine-native federation / bootstrap-once
  / ephemeral target / un-automatable), discover them at planning time, curate the
  human-verified ones, and keep VAL-3 honest when access can't be obtained — never
  faking a login. Reuses the existing credential vault and the never-overclaim gate.
- **Live execution diagrams** — clicking any plan, coding, or testing task in the
  CFactory cockpit opens an animated dependency-graph of that work, rendering
  whichever stage is furthest along (test → code → plan) from a shared `graph`
  field on `/api/workitems/{key}/process`. PFactory exposes the epic-children DAG,
  AIFactory the per-subtask `depends_on` + timing, TFactory the per-subtask lane +
  timing; the cockpit animates nodes (done / active / failed / stalled) with live
  per-node timers. See the
  [design](plans/2026-06-14-live-execution-diagrams.md) (shipped v1).
- **Completion evidence gates** — a stage may claim "passed" only with proof it ran
  (issues created · non-zero tokens + phases · non-null verdict + tests executed),
  implemented across PFactory, AIFactory and TFactory; consumers treat
  success-without-evidence as unproven, never green. See
  [RFC-0001a](rfc/0001a-completion-evidence-gates.md).
- **Security + CI hardening wave** — a 16-agent deep audit (epic Factory#45)
  drove GitHub Actions script-injection fixes and the CVE-2025-66032 `[bot]`-suffix
  copilot fix across repos, PFactory's bashlex command-allowlist AST parser
  (closing a `$()`/pipe IMDS-exfil bypass), fail-closed `/mcp` and `DISABLE_AUTH`
  boot guards, TFactory SSRF guards, and CFactory's first test CI gate.
  **Branch protection is on**, so "auto-merge on green" can no longer merge red,
  and a reusable PARR seam-regression check became a post-deploy gate.
- **Per-worker, per-provider observability** — AIFactory already ran parallel
  multi-provider coding workers; now you can **see** them. Per-worker capture in
  the v1.3 completion event (`workers[]` / `by_provider` / `by_model`), real
  OpenTelemetry per-worker metrics from the web-server (bounded cardinality, no
  `task_id`), live worker + 10s heartbeat events, a **soft (observe-only) budget
  alert**, and a **live CFactory cockpit** with a ticking per-task cost stamp and
  per-worker drill-down. **OpenObserve** is bundled as the OTLP backend behind
  CFactory's ingress (Keycloak SSO + Cloudflare tunnel), so
  `OTEL_EXPORTER_OTLP_ENDPOINT` points at CFactory without it reinventing a TSDB.
  See the [blog](/blog/2026/06/13/seeing-the-factory-think-per-worker-observability/).
- **Code-aware planning** ([RFC-0010](rfc/0010-code-aware-planning-and-behavioral-equivalence.md)) —
  PFactory reads the target repo statically (never executing it) and emits a
  *delta-aware* plan: real `files_to_modify`, language taken from the repo (not
  guessed), a grounded change footprint the human approves, and — for a language
  rewrite — a behavioral-equivalence lane that proves the new impl matches the
  original. Brownfield + Python→Rust.
- **Trusted-plan fast path** — PFactory signs an RFC-0002 contract; AIFactory
  verifies it and **skips planning** (proven: build codes to completion). Gemini
  is selectable through the contract (`PFACTORY_EXECUTION_MODEL`).
- **Verify leg closed** — TFactory's planner auto-runs on ingest (#347) and the
  handoff carries the signed contract + deployed URL (#547), so it tests the
  **declared** acceptance criteria against the **real** build.
- **Deploy-then-verify on real AWS** — deterministic, cost-guarded App Runner
  deploys (teardown always ships with deploy); the live API and **authenticated
  web UIs** are tested against the running deployment, with **screenshots +
  findings** as proof. See the [Pipeline & Guards](/pipeline/) reference and the
  [blog](/blog/).
- **OAuth-only by default** — agents never silently bill a stray API key
  (direct-key billing is an explicit opt-in).

## Now — standardize the PARR spine

The connective tissue that lets the four products cooperate, tracked as the
[PARR-spine epic]({{ site.repo_url }}/issues):

- **PFactory → AIFactory** inbound handoff with issue-number provenance
- A shared **correlation key** (the GitHub issue number) threaded end-to-end
- A normalized **completion-event** envelope across all three services
- A canonical local **port map** (AIFactory 3101 · PFactory 3114/3115 · TFactory 3103 ·
  CFactory 3110/3111)

## Next — CFactory cockpit

The control tower shipped as a multi-view cockpit (Services, Pipeline board,
Copilot, Audit — see the [cockpit tour](/cfactory/)). Phases, tracked in the
[CFactory repo](https://github.com/olafkfreund/CFactory/issues):

- **P1 (shipped)** — skeleton, WorkItem correlation store, read-only pipeline board
- **P2 (shipped)** — agentic copilot (read tools, timeline summaries, anomaly detection)
- **P3** — advise + confirm actions, audit, scoped keys
- **P4** — hardening for hosted / multi-tenant

## Ongoing — the products

- **PFactory** — deeper cloud/Backstage enrichment, living templates, more review lenses
- **AIFactory** — provider delegation, enterprise hardening, mission-control UX
- **TFactory** — more modality lanes, richer evidence, tighter handback loop

## The bet

Lead with **governance + verification + observability**. Execution is
commoditizing; the durable advantage is a factory you can trust and watch.
CFactory is how the suite proves it.

---

*Live status lives in the issues and the
[program board](https://github.com/users/olafkfreund/projects/1).*
