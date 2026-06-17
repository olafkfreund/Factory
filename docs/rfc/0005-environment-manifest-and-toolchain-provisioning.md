---
layout: default
title: "RFC-0005: Environment Manifest & Ephemeral Toolchain Provisioning"
permalink: /rfc/environment-provisioning/
---

# RFC-0005 — Environment Manifest & Ephemeral Toolchain Provisioning

> **Status:** Proposed · **Created:** 2026-06-15 · **Updated:** 2026-06-15 · **Affects:** PFactory (planner), AIFactory (coder), TFactory (verifier), RFC-0002 Task Contract
> **Implementation note (2026-06-15):** the sandbox substrate is no longer just a proposal. The `factory-sandbox` primitive (`scripts/factory_sandbox.py`) and the verification runner/gate/profiles (`scripts/verification_{runner,gate,profiles}.py`) are landed, and the **k8s Job-per-task backend is live in AIFactory** (`core/kube_sandbox.py`) — originally scoped as Phase 5, it was brought forward (see §3.3 and the phase table). The contract `environment` block (Phase 0) is **landed (2026-06-16)** as `$defs.environment` in `apis/task-contract.schema.json` (optional, additive; constraints exercised by `scripts/validate_task_contract.py`).
> The single biggest gap in "we control the whole process": a task that needs a
> toolchain or library we did not pre-install fails silently or not at all. This
> RFC makes the **environment a declared, contracted, verifiable artifact** that
> AIFactory and TFactory materialize identically — on demand, isolated, and torn
> down.

## 1. Motivation — the toolchain gap

Two concrete failures, both observed on the live fleet (2026-06-14):

- **AIFactory** could write Rust/Go/Java/C++ but not build or test it —
  `cannot execute cargo, permission denied` — because the toolchains were not in
  the coder image. We patched it by `apk add`-ing six toolchains into the
  Dockerfile (`AIFactory/Dockerfile:110-116`). That "bake everything in" approach
  does not scale: it bloats one image ~1.5 GB, can never cover a pinned JDK 17 vs
  21, Elixir, Haskell, an old Node, a CUDA lib, or a system `.so` a package needs;
  and the only way to add anything is a full image rebuild + redeploy.
- A successful build can still be mis-reported because nothing **checks** the
  environment was real (see RFC-0001a for the completion-side analogue).

### Where each service stands today (code-grounded)

| | AIFactory (build) | TFactory (verify) |
|---|---|---|
| Where the agent/runner runs | **In-process SDK subprocess of one long-lived Deployment pod** (`agents/session.py:14`, `core/client.py:1079`). No per-task container. | **Ephemeral `docker run --rm` container per lane** (`tools/runners/docker_runner.py:209-310`, `lane_dispatch.py:142-159`). Hardened: `--network none --read-only`, CPU/mem/PID caps, non-root, ro-`/work` + rw-`/scratch`. |
| Where toolchains come from | **Statically baked** in `Dockerfile` (`apk add go-1.25 rust-1.90 maven-3.9 openjdk-21-default-jdk cmake build-base`). No runtime install. | **Pre-baked per-(language,framework) images** (`tfactory-runner-pytest/jest/playwright/java`), keyed by `lang_registry.py` + `RuntimeSpec.image`. App build delegated to the repo's `.tfactory.yml` / Dockerfile on the host (`build_runner.py:38-54`). |
| What the plan already declares | The **verification commands** are extracted from the plan and sanitised into a per-worktree allowlist (`security/plan_commands.py`; `PLAN_GRANTABLE_COMMANDS` = `{uv,pytest,cargo,go,mvn,gradle,ctest,make,…}`). | Consumes the language from the contract; raises `UnsupportedLanguageError` for anything without a runner image. |
| Gap | No per-task container, **no dynamic provisioning** → absent toolchain = hard fail. | Same provisioning gap (no on-demand image/build); app-build toolchain is whatever the repo/host has → drift risk vs the build env. |

**Two facts make the fix tractable:** (1) the planner already knows the language
and the exact build/test commands; (2) TFactory already owns a hardened
ephemeral-container primitive (`DockerRunner`) that AIFactory lacks. We reuse
both.

## 2. How the field solves this (research)

- **Per-task disposable sandbox is the industry standard.** OpenHands, SWE-agent,
  and Devin each run a task in its **own Docker container**, not a shared
  long-lived host. OpenHands additionally supports a repo-level
  **`.openhands/setup.sh`** that runs *before* the agent — "install dependencies,
  set env vars" ([OpenHands repo customization](https://docs.openhands.dev/openhands/usage/customization/repository)).
- **Declarative environment manifests** — `devcontainer.json` (OS, runtimes,
  CLIs, features, lifecycle scripts; consumed by Codespaces/DevPod/devcontainer
  CLI — [spec](https://containers.dev/implementors/json_reference/)) and **Nix
  flakes** (hermetic, version-pinned via `flake.lock`, binary-cached, **no global
  install**, GC'd after use — [Nix flakes in CI](https://medium.com/@kaushalsinh73/6-nix-flakes-rituals-to-stabilize-ci-cd-b66f1ffe64b1)).
- **Auto-detection** — Nixpacks (Railway) and Cloud-Native Buildpacks detect ~20
  languages and produce a build image with no manifest ([Nixpacks](https://kinsta.com/changelog/nixpacks/)).
- **Ephemeral k8s** — Pods/Jobs spun per task and GC'd ([Qovery](https://www.qovery.com/blog/ephemeral-environments)).

**Takeaway:** the controlled answer = a *declared* environment + a *disposable,
isolated* runner that materializes exactly that environment. We adopt it, with
**Nix as the hermetic primary engine** (fits a NixOS-operated fleet) and the
container catalog as the fast path.

## 3. Design

### 3.1 The Environment Manifest (the single source of truth)

A structured `environment` block added to the **RFC-0002 Task Contract** — the
one artifact that already flows PFactory → AIFactory → TFactory, so the build env
and the verify env **cannot drift**.

```json
"environment": {
  "language": "rust",
  "toolchain": { "rust": "1.90", "cargo": "1.90" },
  "system_packages": ["pkg-config", "openssl-dev"],
  "build_commands": ["cargo build"],
  "verify_commands": ["cargo test"],
  "provisioning": {
    "method": "nix | devcontainer | image | setup_script",
    "ref": "flake.nix | .devcontainer/devcontainer.json | ghcr.io/.../rust:1.90 | .factory/setup.sh",
    "generated": true
  },
  "network": "none | restricted",
  "proof": { "verify": ["cargo --version", "rustc --version"] }
}
```

- **Who writes it:** the **planner** (PFactory / AIFactory planner phase). It
  already extracts language + commands; it now also resolves the toolchain +
  versions (from the spec's acceptance criteria and a `lang_registry`) and picks a
  `provisioning.method`. When the repo has no `flake.nix`/`devcontainer.json`, the
  planner **generates one** and commits it as part of the deliverable.
- **Why a manifest, not "install in the shared pod":** installing into the shared
  long-lived pod pollutes it, races other tasks, and is blocked by the bwrap
  sandbox/egress policy. The manifest instead drives provisioning of an
  **isolated, throwaway environment** — the install happens there, not in the
  shared pod.

### 3.2 Provisioning engine — tiered, deterministic

A new `environment/provisioner.py` (shared library, vendored into AIFactory and
TFactory) resolves a manifest into a ready-to-run sandbox:

1. **Tier A — Nix (preferred, hermetic).** If `provisioning.method == "nix"`,
   materialize via `nix develop -c <cmd>` / `nix shell`. Hermetic, pinned by
   `flake.lock`, binary-cached (`cache.nixos.org` + our own cachix), **no global
   install**, GC'd after. This is the "control everything + reproducible" tier and
   the deliverable doubles as the provisioning spec.
2. **Tier B — image catalog (fast path).** A registry of base images per
   `(language, version)` — a generalization of TFactory's existing
   `tfactory-runner-*` catalog. The manifest selects the tag; the runner launches
   it. Covers the common 80%.
3. **Tier C — on-demand build (long tail).** When no catalog image fits, build a
   per-task image from the manifest's `system_packages` + toolchain (or
   Nixpacks-style auto-detect), **content-addressed and cached** so the second run
   is instant.
4. **Tier D — in-container setup script (last resort).** Run the repo's
   `.factory/setup.sh` (à la OpenHands) **inside** the ephemeral container — never
   on the shared host.

### 3.3 Execution model — one ephemeral-runner primitive, two consumers

**Reuse, don't reinvent:** extract TFactory's `DockerRunner`
(`tools/runners/docker_runner.py` — SDK-free, argv-only, podman-swappable,
already hardened) into a **shared `factory-sandbox` primitive**.

- **AIFactory** stops running build/verify commands directly in the shared pod.
  The coder's worktree is bind-mounted **rw** into a per-task ephemeral container
  materialized from the manifest (Tier A–D); `cargo build`/`pytest`/etc. run
  there with the right toolchain and are torn down after. (The LLM/agent loop can
  stay in the backend pod; only the *execution* of build/verify/test commands
  needs the toolchain, so moving just those into the sandbox is the minimal,
  lowest-risk change. A later step can move the whole coder session in.)
- **TFactory** already runs lanes this way; it gains (a) the manifest-driven
  **app build** running in the same env (closing the build/verify drift), and (b)
  an **extensible/on-demand catalog** so an unrequested language no longer dead-ends
  at `UnsupportedLanguageError`.

> **Container vs fresh k8s Pod/Job?** Start with `DockerRunner`-style ephemeral
> containers on the node — it is proven in TFactory today, SDK-free, and
> podman-rootless capable. A **k8s Job-per-task** is the heavier alternative for
> stronger isolation and horizontal scale, behind the same `factory-sandbox`
> interface.
>
> **Shipped (2026-06-15):** the k8s Job backend is live in AIFactory
> (`core/kube_sandbox.py` + `agents/gate_runner.py`), because the AIFactory pod has
> no container runtime of its own — so the in-cluster path was needed before the
> node-container path. Each gate runs as an ephemeral Job (`backoffLimit: 0`,
> `ttlSecondsAfterFinished: 120`, `restartPolicy: Never`,
> `automountServiceAccountToken: false`, `ghcr-pull` secret, CPU/mem limits) under
> a dedicated `aifactory-sandbox` ServiceAccount + Role (create/get/list/watch/
> delete jobs; read pod logs) provisioned in gitops. The Job **co-mounts the task
> worktree** at `/work` via the `aifactory-data` PVC `subPath` — derived by
> stripping the data root (`AIFACTORY_DATA_ROOT`, default
> `/home/nonroot/.aifactory`) from the gate's cwd — so code-reading gates
> (lint/test/build) run against real files, not just toolchain checks. Proven live:
> a gate Job ran `go test -v ./...` green against a real co-mounted worktree.
> Routing is opt-in/default-off via `AIFACTORY_SANDBOX_GATES` +
> `AIFACTORY_SANDBOX_BACKEND` (`docker`|`kubejob`) + `AIFACTORY_SANDBOX_IMAGE`.
> Honest caveats: the kubejob backend takes **one** toolchain image per call (no
> per-language multiplexing yet), reports a synthetic 0/1 rather than the
> container's real exit code, and the PVC co-mount relies on a single-node /
> `local-path` cluster.

### 3.4 The evidence gate — materialize-or-HALT

Before coding/verifying, the provisioner runs `environment.proof.verify`
(`cargo --version`, `javac -version`, …). If the toolchain does not materialize,
the task **HALTs with a structured `environment_unavailable` reason** and surfaces
in the cockpit — instead of the silent `cannot execute cargo` we saw. This mirrors
RFC-0001a: no environment, no green.

## 4. Why this answers the original questions

- *"Should planning find out and curate a task to install before coding?"* —
  Planning **declares** the environment (it already declares commands); it does
  **not** emit a "install into the shared pod" step. The manifest drives isolated
  provisioning.
- *"Can we branch out into a fresh pod with a throwaway session that has
  everything?"* — Yes; that is the core of §3.3, and it is what OpenHands/Devin do.
  We implement it with the container primitive we already own.
- *"How do we make sure we have what we need?"* — The manifest + evidence gate:
  the env is declared, materialized, and **proven** before work starts.
- *"Same for TFactory testing?"* — The manifest is the **shared** contract field;
  AIFactory and TFactory materialize the identical environment, so the code builds
  the same way it is tested.

## 5. Phased plan

| Phase | Scope | Risk | Value |
|---|---|---|---|
| **0** | Manifest schema in RFC-0002 + `environment_unavailable` evidence gate (planner emits it; runners read it; HALT-on-missing). No execution change yet. | low | Turns silent toolchain failures into surfaced, contracted decisions immediately. |
| **1** | Extract TFactory `DockerRunner` → shared `factory-sandbox`. AIFactory runs build/verify in an ephemeral **catalog image** (Tier B) selected by the manifest. | med | AIFactory gains per-task toolchains without image bloat; reuses proven code. |
| **2** | **Nix engine** (Tier A): `nix develop` provisioning; planner generates a `flake.nix` when absent. Hermetic, pinned, cached. | med | The "control everything + reproducible" tier; removes the static image entirely over time. |
| **3** | On-demand image build + content-addressed cache (Tier C) for the long tail. | med | Any toolchain, no rebuild-the-fleet. |
| **4** | TFactory: app build runs in the manifest env; catalog becomes extensible/on-demand; unify the engine with AIFactory. | med | Closes build/verify drift; no more `UnsupportedLanguageError` dead-ends. |
| **5** (opt-in) | k8s **Job-per-task** backend behind `factory-sandbox` for heavy isolation/scale. **Shipped early (2026-06-15)** in AIFactory with worktree co-mount — see §3.3; the AIFactory pod has no node runtime, so this path landed first. | high | Scale + hard isolation when needed. |

**Start at Phase 0** — it is small, additive, and immediately converts today's
silent failures into controlled, visible ones, while the schema it lands is the
contract everything else builds on.

## 6. Alternatives considered

- **Keep baking toolchains into the image** (status quo). Rejected: unbounded
  image growth, no version pinning, fleet rebuild per addition, cannot cover the
  long tail.
- **Per-task `apt/apk install` in the shared pod before coding.** Rejected:
  pollutes the long-lived pod, races concurrent tasks, blocked by the
  sandbox/egress policy, not reproducible.
- **k8s Job-per-task as the default.** Deferred to Phase 5: heavier and slower to
  build than reusing the existing `DockerRunner`; valuable only at scale.

## 7. Files to build on

AIFactory: `core/worktree.py`, `core/client.py` (sandbox toggle + cwd),
`security/plan_commands.py` (already extracts commands — extend to the manifest),
`Dockerfile` (shrinks as Nix/catalog take over). TFactory:
`tools/runners/docker_runner.py` (→ shared primitive), `lane_dispatch.py`,
`lang_registry.py`, `framework_registry/descriptor.py`, `build_runner.py`.
New shared lib: `environment/{manifest,provisioner}.py`.
