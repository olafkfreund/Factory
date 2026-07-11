# Sandbox runtime-class evaluation: gVisor/Kata for per-task Jobs

> Issue: #274 (parent: #270)
> Date: 2026-07-11
> Status: **Decision made — DEFER** (with a narrow optional adopt path and a
> compensating-controls checklist below)

## 1. Scope and question

2026 consensus for executing untrusted or AI-generated code is a microVM
(Firecracker/Kata) or gVisor as the isolation boundary; hardened containers
with bubblewrap are treated as an inner layer only. Factory's current model is
unprivileged bwrap in-pod (AIFactory #363) on k3d. This document answers:
should Factory adopt a `RuntimeClass` (gVisor `runsc` or Kata) for the
per-task Jobs that execute untrusted code, or explicitly defer with
compensating controls?

Evidence was gathered on a **local scratch k3d cluster** (never the live
factory cluster), same substrate class as production: k3d v5.7.4, k3s
v1.30.4+k3s1, containerd CRI v2 config, gVisor `runsc` release-20260706.0
(static release binaries), default `systrap` platform.

## 2. Trust-boundary inventory

Which workloads execute untrusted (AI-generated or SUT-supplied) code today,
and what each currently relies on:

| # | Workload | Where | Untrusted input | Current controls |
|---|----------|-------|-----------------|------------------|
| 1 | Coder agent bash commands | AIFactory control-plane pod (Deployment, long-lived) | AI-generated shell commands, code under construction | bwrap wrapper per command (#363): `--die-with-parent --unshare-ipc --unshare-uts --dev /dev --tmpfs /tmp`, worktree rw / everything else ro; opt-in `--unshare-pid` + fresh `/proc`; opt-in `strict` mode adds `--unshare-net`. Non-root pod. Chart `sandbox.gvisor.*` toggle exists for THIS pod (Helm, default off). |
| 2 | Per-task build Jobs (packed path, RFC-0017) | AIFactory `core/job_dispatch.py` k8s Jobs | AI-generated code built and executed inside `nix develop` | Non-root (Wolfi) image, `automountServiceAccountToken: false`, resource limits, `backoffLimit: 0`, `activeDeadlineSeconds`, TTL. No `securityContext`, no `runtimeClassName`. Shared warm `/nix/store` PVC mounted rw. |
| 3 | Verify Jobs: orchestration + per-lane test Jobs | TFactory `agents/verify_dispatch.py`, `tools/runners/kube_sandbox.py` | Executes the SUT's own tests and code (`nix develop` per lane) | Same shape as row 2 (mirrors AIFactory #686/#671). Shared warm `/nix/store` PVC. |
| 4 | Deploy-lane Jobs (RFC-0013, DRY-RUN) | TFactory `agents/deploy_lane.py` via nix Job | Untrusted IaC; `tofu init` downloads and runs provider plugins selected by that IaC | Same Job substrate as row 3. Provider binaries are code execution chosen by the untrusted input — the strongest argument on this list for a hard boundary. |
| 5 | Regression CronJob / portal-UI (playwright) Jobs | TFactory | Repeated execution of SUT test suites, browser automation | Same Job substrate (nix). |
| 6 | Planning / portals | PFactory, CFactory | LLM output only, no arbitrary code execution | Out of scope for a runtime class. |

Two observations from the inventory before any experiment:

- Everything in rows 2-5 — i.e. every per-task Job — runs its payload inside
  `nix develop` on the nix-runner image. A runtime class that cannot run Nix
  local builds cannot cover any per-task Job.
- The chart `NetworkPolicy` templates (AIFactory and TFactory) select pods by
  the Helm `selectorLabels` (`app.kubernetes.io/name` / `instance`). The
  per-task Job pods carry only `app: <service>` + `factory.io/*` labels, so
  **Job pods are not covered by any NetworkPolicy today**. See checklist.

## 3. What was tested (local scratch k3d)

Setup: static `runsc` + `containerd-shim-runsc-v1` mounted into the k3d node,
k3s `config.toml.tmpl` extended with the `runsc` runtime
(`{{ template "base" . }}` + `io.containerd.runsc.v1`), `RuntimeClass gvisor`
applied. Smoke pod confirmed the sandbox is real (`dmesg` -> "Starting
gVisor...", kernel reports `4.19.0-gvisor`).

### 3.1 bwrap inside gVisor (the #363 flag set)

Run as non-root (as the agent actually runs; unprivileged bwrap implicitly
creates a user namespace):

| Mode | Flags | Result under gVisor |
|------|-------|---------------------|
| fs (default) | `--unshare-ipc --unshare-uts --dev --tmpfs /tmp` + ro-binds + worktree rw | **works** |
| pid (opt-in) | fs + `--unshare-pid --proc /proc` | **works** |
| strict (opt-in) | fs + `--unshare-net` | **fails**: `bwrap: loopback: Failed RTM_NEWADDR: No child process` — gVisor netstack rejects the netlink call bwrap uses to bring up loopback |
| userns prereq | `unshare -Ur true` | works (gVisor supports nested user namespaces) |

Caveat: run as uid 0 without `CAP_SYS_ADMIN`, bwrap fails under both runc and
gVisor ("Creating new namespace failed") — not a gVisor delta, just a
reminder the agent must stay non-root for bwrap to work anywhere.

### 3.2 Nix under gVisor (the per-task Job substrate)

Identical pods on `nixos/nix:2.24.9`, runc vs gvisor:

| Operation | runc | gVisor |
|-----------|------|--------|
| `nix build` trivial `runCommand`, `sandbox=false` | ok (1s) | **fails** |
| same, `sandbox=true` | ok (1s) | **fails** |
| `nix develop ... -c echo ok` (mkShell) | ok | **fails** |
| Evaluation, flake ops, binary-cache substitution (network) | ok | ok |

The failure is precise and consistent: evaluation and downloading from
cache.nixos.org succeed; the local **builder child fails to initialize**:

```
... while waiting for the build environment for '/nix/store/...-nix-shell-env.drv'
    to initialize (succeeded, previous messages: )
error: reading a line: Input/output error
```

`nix develop` always realizes its `nix-shell-env` derivation locally, so this
is not avoidable by substitution — **every TFactory verify lane, AIFactory
packed build Job, and deploy-lane Job would fail under gVisor today.** This
is a Nix-builder/gVisor incompatibility (builder child handshake over the
pty/fd protocol), not a networking or policy issue.

### 3.3 Overhead

Pod create-to-completed for a pre-pulled trivial image, 3 runs each:
runc 2.0-3.0s, gVisor 2.9-3.1s. Roughly **+1s per Job** — negligible against
multi-minute verify Jobs. Overhead is not a reason to defer; compatibility is.

### 3.4 Kata Containers

Not tested, by reasoning rather than time: Kata needs a VMM and `/dev/kvm`
inside the node. Factory nodes are k3d containers (k3s-in-docker), so Kata
requires nested virtualization plumbed through the node container plus a
kernel/initrd per pod — a substrate change, not a runtime-class toggle. On
the current single-remote-node k3d cluster (p510) this is out of reach without
moving to bare-metal k3s or VM-backed nodes. Revisit only if the cluster
substrate changes.

## 4. Decision: DEFER, with an explicit re-evaluation trigger

**Defer adopting a gVisor/Kata RuntimeClass for per-task Jobs.**

Rationale (evidence above):

1. Nix local builds — the substrate of 100% of the per-task Jobs — fail under
   gVisor (3.2). There is no per-task Job type today that a gVisor runtime
   class could cover.
2. Kata is blocked by the k3d substrate itself (3.4).
3. The bwrap inner layer, which does work today, would partially regress
   under gVisor (`strict` no-egress mode breaks, 3.1) — so even a hybrid
   "gVisor outside, bwrap inside" loses a control we currently have.
4. Overhead is NOT a factor (+1s, 3.3) — if compatibility arrives, adoption
   is cheap.

What we are NOT deferring:

- The AIFactory chart already ships `sandbox.gvisor.enabled` for the
  control-plane Deployment (epic #35 #37) and the agent's bash-allowlist
  workload is exactly the profile that did work in 3.1 (bwrap fs/pid modes
  fine under gVisor). Operators on gVisor-capable clusters can turn that on
  today, with one caveat to document: `sandbox.mode=strict` (bwrap
  `--unshare-net`) is incompatible with gVisor — use fs/pid mode plus a
  NetworkPolicy for egress control instead.
- The compensating controls below, several of which are cheap and currently
  missing.

Re-evaluate (reopen against #270) when ANY of:

- gVisor fixes the Nix builder-init incompatibility (retest is one scratch-k3d
  afternoon; keep the config.toml.tmpl recipe from this doc);
- Factory moves off k3d to bare-metal k3s or VM nodes (unlocks Kata for the
  deploy lane, the strongest candidate because `tofu init` executes
  input-selected provider binaries);
- a non-Nix per-task Job type appears (it could adopt the runtime class
  immediately behind a Helm value, following the existing `sandbox.gvisor.*`
  pattern).

## 5. Compensating controls checklist (defer path)

Status legend: `[x]` verified in current deployment, `[ ]` gap to close.

- [x] bwrap wrapping of every agent bash command, default-on in Helm
  (AIFactory #363); worktree-only rw, private IPC/UTS, tmpfs /tmp.
- [x] Non-root task images (Wolfi/Chainguard nonroot) — also a bwrap
  prerequisite (3.1 caveat).
- [x] `automountServiceAccountToken: false` on per-task Job pods (no k8s API
  credential inside the untrusted context).
- [x] `backoffLimit: 0`, `activeDeadlineSeconds`, `ttlSecondsAfterFinished`,
  cpu/memory limits on Jobs (bounded blast radius in time and resources).
- [x] Real OS sandbox in the agent pod validated by an escape-test corpus
  (AIFactory `test_sandbox_escape_corpus.py`).
- [ ] **NetworkPolicy coverage for per-task Job pods.** The chart policies
  select Helm `selectorLabels`; Job pods (`app: <service>`,
  `factory.io/kind: task`) match nothing. Add a policy selecting the Job
  labels: default-deny ingress, egress limited to DNS, the binary caches,
  git remotes, and the service API needed to report results.
- [ ] **Pod `securityContext` on Job specs.** Cheap win: `runAsNonRoot: true`,
  `allowPrivilegeEscalation: false`, `capabilities: {drop: [ALL]}`,
  `seccompProfile: RuntimeDefault` in `job_dispatch.py` /
  `verify_dispatch.py` / nix Job builders. Today the non-root guarantee
  comes only from the image, and no seccomp profile is pinned.
- [ ] **Shared warm `/nix/store` PVC is write-shared across tasks.** A
  malicious task can tamper store paths consumed by later Jobs
  (cross-task cache poisoning). Mitigations in preference order: mount the
  warm store read-only into task Jobs with an overlay/local scratch store;
  or periodic `nix store verify --all` against upstream caches; at minimum
  document the shared-cache trust assumption.
- [ ] **Missing doc:** AIFactory `values.yaml` references
  `guides/security/gvisor.md` which does not exist; the gVisor caveats
  (no `strict` bwrap mode, no Nix builds) belong there.
- [ ] Document in the threat model that per-task isolation is
  namespaces + non-root + policy, NOT a syscall/VM boundary, and that
  hostile-tenant workloads are out of scope until section 4's triggers fire.

## 6. Reproduction recipe (for the retest afternoon)

```sh
# static binaries
curl -LO https://storage.googleapis.com/gvisor/releases/release/latest/x86_64/runsc
curl -LO https://storage.googleapis.com/gvisor/releases/release/latest/x86_64/containerd-shim-runsc-v1
chmod +x runsc containerd-shim-runsc-v1

# k3s containerd template (config version 2)
cat > config.toml.tmpl <<'EOF'
{{ template "base" . }}

[plugins."io.containerd.grpc.v1.cri".containerd.runtimes.runsc]
  runtime_type = "io.containerd.runsc.v1"
EOF

k3d cluster create sandbox-eval --no-lb \
  -v $PWD/runsc:/usr/local/bin/runsc \
  -v $PWD/containerd-shim-runsc-v1:/usr/local/bin/containerd-shim-runsc-v1 \
  -v $PWD/config.toml.tmpl:/var/lib/rancher/k3s/agent/etc/containerd/config.toml.tmpl

kubectl apply -f - <<'EOF'
apiVersion: node.k8s.io/v1
kind: RuntimeClass
metadata:
  name: gvisor
handler: runsc
EOF
# then: pod with runtimeClassName: gvisor; pass = dmesg says "Starting gVisor..."
# retest gate: nix develop --impure --expr 'with import <nixpkgs> {}; mkShell {}' -c true
```
