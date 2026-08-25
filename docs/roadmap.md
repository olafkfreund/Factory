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

## Recently shipped (July 2026)

260 issues closed across the five repositories this month. The theme was not new
capability — it was **making the existing signals honest**.

- **Multi-provider git + tenant-configured projects**
  ([RFC-0020](rfc/0020-multi-provider-git-integration-and-tenant-configured-projects.md),
  *implemented* — epic #361 and all phases closed, including Phase 8 for multiple
  git connections per tenant). Repositories and credentials are configured per
  tenant in the portal rather than baked into env.
- **Continuous regression verification**
  ([RFC-0018](rfc/0018-regression-suite-and-continuous-verification.md),
  *implemented*) — TFactory runs a standing regression suite, so a green verdict
  now means "and nothing that used to pass has broken".
- **Job-native defaults flipped live** ([RFC-0017](rfc/0017-full-job-native-execution-and-scale-out.md)) —
  the build and verify defaults that were converging in June are now on.
- **CloudEvents cutover** — the legacy completion envelope is gone; every service
  speaks one event format, consumer-first so nothing broke on the way.
- **Competitive-gap remediation** (epic #270) — benchmark harness, cost-aware
  model routing, prompt-injection defences, dependency gating, multi-vote judging.
- **Pre-demo hardening** (epic #241) — closing the honesty gaps before anything is
  shown to anyone.
- **Compliance program under way** (epic #310) — governance/ISMS, change
  management and separation of duties, incident response with SEC/NIS2 timelines,
  and agentic-AI governance (model registry, eval gates) all closed. Seven further
  epics remain open and are the current programme spine.

### The honesty sweep

A run of defects found this month shared one shape: **a gate that reported success
without checking anything**. They are listed together because the pattern matters
more than any single fix.

| Reported | Actually |
|---|---|
| PARR seam smoke gate green on every deploy | it crashed before its first request (#416) |
| two drift gates green | one service was 181 lines behind the canonical (#402) |
| a UI drift checker passing | its guard was defined and never called (#401) |
| `Synced / Healthy` from GitOps | a commit behind, twice in one day (#425) |
| a build reporting `human_review` | it wrote no code at all (AIFactory#1070) |
| `all_verified: true` from the verify leg | the spec body never reached it (TFactory#855) |

These are now tracked as one programme: **[epic #431](https://github.com/olafkfreund/Factory/issues/431)
— silent fallbacks**, backed by an AST sweep of all five repositories. Of 158
candidate sites, 19 default to a value that *asserts progress or success* where
the truth is unknown. A crash is cheap because it names its own cause; a
plausible wrong value survives, propagates, and surfaces far from where it
started.

### Also landed

- **Security** — credential-bearing request models no longer render secrets in
  their `repr` (#377); frontend lockfile vulnerabilities are gated in every repo,
  not just one (#386); `apps/web-server` is lint- and format-gated in AIFactory
  (#384); MIT licences added where they were missing (#387).
- **Operational reliability** — a CronJob can no longer fail silently for weeks
  (#381); the CLIs are baked into the image rather than installed per run (#383);
  workspace storage moved to RWX so tasks stop stranding on node-local volumes.
- **Orphaned-task reaping** (AIFactory#1064) — tasks whose worker died no longer
  sit on the board looking busy. Machine-owned states are reaped after an idle
  threshold; tasks awaiting a **human** are never reaped at any age, because age
  alone cannot tell a dead task from a patient one.
- **Approve actually approves** (AIFactory#1071/#1073/#1076) — the Approve button
  did the git work, never advanced the task, and under the Job-based build backend
  could not identify the branch at all. It now merges the pull request and records
  the result.

## Previously shipped (June 2026)

The PARR spine is now proven end-to-end on real infrastructure:

- **Spec-driven interop** ([RFC-0015](rfc/0015-spec-driven-interop-and-validated-gap-features.md),
  *implemented* — epic #183 + all 10 children closed) — the fleet now reads and
  emits SpecKit-style specs (a `constitution` of house rules ingested by PFactory
  and consumed by AIFactory/TFactory, plus `.specify` ingest/emit), with an
  adversarial spec-review pass, requirement→test traceability, and a declarative
  extension registry. End-to-end proof landed 2026-06-21.
- **Horizontal & concurrent execution** ([RFC-0016](rfc/0016-horizontal-concurrent-execution.md),
  *core implemented & verified live* — epic #188) — a stateless control plane with
  durable Postgres job-state, admission/concurrency caps tied to the cost budget,
  the Nix-per-task Kubernetes Job substrate as the default for build/verify gates,
  a shared MinIO/S3 object store for artifacts, and KEDA queue-depth autoscaling.
  Proven live on the factory cluster: **8 concurrent** Job-per-task runs and a
  **KEDA 1→3** scale-out.
- **Job-native execution mechanisms** ([RFC-0017](rfc/0017-full-job-native-execution-and-scale-out.md),
  epic #206) — Job-native log streaming, a Redis-backed multi-replica
  run-multiplexer, and workspace pack/unpack via object storage. The build and
  verify *default* flips were still converging at the end of June; they went
  **live in July** (see above). Multi-node workspace consumption remains.
- **AWS demo resources cleaned up** — the App Runner / EKS demo stacks were torn
  down; zero ongoing cloud spend.

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

## Now — compliance and audit-readiness

The PARR spine and the CFactory cockpit are both shipped; the current programme
is [epic #310](https://github.com/olafkfreund/Factory/issues/310), audit
readiness for ISO 27001 / SOC 2. Four of its epics closed in July. Seven remain,
and they are the near-term sequence:

- **IAM & access control** (#312) — enforce MFA, retire the shared wildcard
- **Audit logging completeness** (#313) — retention policy, SIEM alerting
- **Encryption at rest & key management** (#314) — DB / MinIO / KMS
- **Secrets management & rotation** (#315)
- **Vulnerability & patch management** (#317) — scan SLAs, evidence
- **Supply-chain integrity** (#318) — SBOM everywhere, signature verification
- **Data governance & PII egress controls** (#320)
- **Runtime isolation & config hardening** (#322) — Job NetworkPolicy
- **Evidence & audit-readiness** (#324) — control-to-framework matrix

Two of these have concrete open findings already: image signature verification
currently fails for **every** fleet image while running in audit mode, so the
policy reports violations and blocks nothing (#430); and five production
CronJobs — including the Postgres backup — exist only as cluster state, not in
git, so they would vanish on a rebuild (#429).

Running alongside: **[epic #431](https://github.com/olafkfreund/Factory/issues/431)**,
the silent-fallback sweep described above.

## Next — seams beyond GitHub

- **Planning from observed infrastructure**
  ([RFC-0024](rfc/0024-planning-from-observed-infrastructure.md)) — RFC-0013 made
  planning deployment-aware from IaC FILES; this reads the account itself, so a
  plan can cite the queue that already exists instead of proposing a new one. The
  credential broker already exists in PFactory and nothing in the planner imports
  it. Strictly read-only, denied by IAM rather than by code, egress off by default.
- **Jira and Bitbucket** ([RFC-0022](rfc/0022-work-item-and-code-seams.md),
  epic #392) — splitting the *work-item* seam from the *code* seam, so the
  factory can plan against a Jira board while coding against a different host.
  RFC-0020 did the code half; this does the work-item half.
- **Earned memory and promotion gates**
  ([RFC-0021](rfc/0021-earned-memory-and-promotion-gates.md), epic #389) — what
  an agent is allowed to remember across runs, and what it must prove before a
  memory is trusted.
- **GTM demos** (epic #240) — the demo set, once the honesty gaps behind it are
  closed.

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
