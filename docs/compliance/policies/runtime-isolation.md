# Runtime Isolation and Config Hardening

- **Domain:** Runtime isolation & config hardening (Factory#322)
- **Frameworks addressed:** ISO/IEC 27001 A.8.22 (segregation in networks) and A.8.9 (configuration management); SOC 2 CC6.6 (boundary protection) and CC6.8 (unauthorized/malicious software controls); PCI DSS Req. 1 (network security controls) and Req. 2 (secure configuration); FedRAMP / NIST 800-53 SC-7 (boundary protection), SC-39 (process isolation), CM-6 (configuration settings).

## Purpose

Factory executes untrusted code by design: AI-generated application code, SUT test suites, and — in the deploy lane — untrusted IaC whose `tofu init` downloads and runs input-selected provider plugins. This document states, for an assessor, the isolation and configuration-hardening controls applied to the pods and Jobs that run that untrusted code, what is verified in the current deployment, and where residual gaps remain. It is honest about the one boundary Factory deliberately does not yet enforce (a syscall/VM sandbox on per-task Jobs) and records the evidence behind that decision.

Scope: the per-task Kubernetes Jobs (AIFactory build/gate Jobs, TFactory verify/deploy/regression lanes) and the AIFactory coder-agent control-plane pod. Out of scope: PFactory planning and CFactory portals, which handle LLM output only and execute no arbitrary code.

## Current state (grounded)

Isolation is layered. Credit is due for a genuinely strong inner sandbox and, since the parent-epic audit, a now-closed set of the cheap Job-manifest controls that were previously flagged missing.

**Inner OS sandbox (bwrap) — strong, default-on.**
The coder agent wraps every bash command in bubblewrap (AIFactory #363). Evidence: `AIFactory/apps/web-server/server/services/sandbox.py`, exercised by an escape-test corpus (`AIFactory/tests/test_sandbox_escape_corpus.py`, `test_agent_sandbox.py`). Flags: `--die-with-parent --unshare-ipc --unshare-uts --dev /dev --tmpfs /tmp`, the active worktree read-write and everything else read-only; opt-in `--unshare-pid` with a fresh `/proc`; `strict` mode adds `--unshare-net` for no egress. Runs unprivileged in-pod (k3d included). Default-on via Helm.

**Fail-closed egress and SSRF guards.**
In-process egress and SSRF guards (fail-closed) constrain outbound calls from the control plane. These complement, but are not a substitute for, network-layer policy on the Job pods (below).

**Per-task Job NetworkPolicies — now shipped, default-on.**
The gap the epic recorded (Job pods matched no NetworkPolicy because they carry `app:`/`factory.io/*` labels, not the Helm `selectorLabels`) is closed:
- AIFactory `charts/aifactory/templates/networkpolicy-tasks.yaml` (#812) selects `factory.io/kind: task`. Default-deny ingress; egress limited to kube-dns (53), 443/tcp to public IPs with RFC1918 (`10/8`, `172.16/12`, `192.168/16`) excepted, and the chart's own API + Postgres. Enabled by default: `networkPolicy.enabled: true` (values.yaml, "ALWAYS enabled in production").
- TFactory `charts/tfactory/templates/networkpolicy-jobs.yaml` (#651) selects `app: tfactory-sandbox` (verify-orchestration, nix lanes, deploy lane). Default-deny ingress; egress to kube-dns, 443/tcp public (RFC1918 excepted), a values-configurable kube API-server rule (nested per-lane Job dispatch), and intra-namespace services (Postgres/MinIO/API). Default-on.

**Per-task Job securityContext — now pinned in the manifest, default-on.**
- AIFactory `apps/backend/core/job_dispatch.py` (#812/#848): container `allowPrivilegeEscalation: false`, `capabilities.drop: [ALL]`; pod `runAsNonRoot: true`, `runAsUser: 65532`, `seccompProfile: RuntimeDefault`; `automountServiceAccountToken: false`; `backoffLimit: 0`, `activeDeadlineSeconds`, TTL, cpu/memory limits.
- TFactory `apps/backend/tools/runners/kube_sandbox.py` (#651/#623): pod `seccompProfile: RuntimeDefault`; container `allowPrivilegeEscalation: false`, drop ALL then a documented, minimal add-back (`DAC_OVERRIDE`, `FOWNER`, `CHOWN`, `SETUID`, `SETGID`, `KILL`) that the nix builder needs against the uid-65532 co-mount. Verify lanes mount no service-account token by default; the deploy lane gets a narrowly-scoped SA only for `kubectl apply --dry-run=server`.

**gVisor RuntimeClass — wired, evaluated, deliberately deferred for Jobs.**
A `sandbox.gvisor.enabled` Helm toggle exists for the AIFactory control-plane Deployment (default off; `runtimeClassName: gvisor`). Its suitability as the per-task Job boundary was tested on a scratch k3d cluster and documented in `Factory/docs/security/sandbox-runtime-class.md` (issue #274), with CI wiring in `AIFactory/.github/workflows/gvisor-smoke.yml`.

## Gaps

The Job NetworkPolicy and securityContext items from the original epic entry are now remediated (above). The residual gaps are the harder isolation boundary and configuration-baseline items.

1. **No microVM / gVisor syscall boundary on per-task Jobs (deliberate defer, documented).** Per-task isolation today is Linux namespaces + non-root + NetworkPolicy + seccomp RuntimeDefault — not a syscall or VM boundary. Evidence-backed reason (`sandbox-runtime-class.md` s3.2): Nix local builds — the substrate of 100% of per-task Jobs — fail to initialize their builder child under gVisor; Kata is blocked by the k3d (k3s-in-docker) substrate lacking `/dev/kvm`. The deploy lane (`tofu init` running input-selected provider binaries) is the strongest exposure and remains under container isolation only. Re-evaluation triggers are recorded (gVisor fixes Nix builder init; move off k3d to bare-metal/VM nodes; a non-Nix Job type appears). Frameworks: SC-39 process isolation, CC6.8, ISO A.8.22.

2. **No `readOnlyRootFilesystem` on per-task build/verify Jobs.** Omitted because nix writes `/nix/var` (builder DB) and tasks write `$HOME` on the rootfs (`job_dispatch.py`, `core/kube_sandbox.py`). The capability exists and is used elsewhere with an immutable rootfs (`factory_sandbox.py`, `docker_runner.py` `read_only_rootfs=True`, e.g. `equivalence_lane.py` with `network=none`), but not on the k8s nix Jobs. Frameworks: CM-6, CC6.8.

3. **TFactory nix lanes run as root with capability add-backs.** `runAsNonRoot` is not enforceable on the nix-runner image (nix realizes local builds via setuid `nixbld` users), so the verify/deploy Job pods run root plus `SETUID/SETGID/DAC_OVERRIDE/FOWNER/CHOWN/KILL`. This is a higher-privilege posture than the AIFactory build Jobs (which run pinned uid 65532) and is the workload that also runs untrusted IaC. Root cause is the Nix build model, which is also why gap #1 cannot currently be closed with gVisor.

4. **Shared warm `/nix/store` PVC is write-shared across tasks.** A malicious task can tamper store paths later Jobs consume (cross-task cache poisoning). Open checklist item (`sandbox-runtime-class.md` s5). Mitigation options: mount the warm store read-only with an overlay/local scratch store; periodic `nix store verify --all`; at minimum document the shared-cache trust assumption. Frameworks: CC6.8, ISO A.8.22.

5. **Egress allowlist is coarse (443 to any public IP).** The Job NetworkPolicies block RFC1918 and default-deny ingress, but permit 443/tcp to `0.0.0.0/0`. There is no per-destination pinning (binary caches, git remotes, LLM APIs) via an egress proxy or FQDN policy, so an untrusted task can still exfiltrate to any public HTTPS endpoint. Frameworks: SC-7, PCI Req. 1, CC6.6.

6. **No PodSecurity Admission backstop on factory namespaces.** Hardening is enforced by the dispatchers writing correct pod specs, not by a cluster admission gate. Only the KEDA namespace carries a PSA label (`factory-gitops/apps/keda/manifests/namespace.yaml`, `enforce: baseline`); the AIFactory/TFactory task namespaces have no `pod-security.kubernetes.io/enforce: restricted`. A dispatcher regression would not be caught at admission. Frameworks: CM-6, CC6.8.

7. **No CIS-benchmark hardening baseline for nodes/cluster.** No evidenced CIS Kubernetes / node-OS benchmark run. Frameworks: CM-6, PCI Req. 2.

8. **Minor: referenced gVisor guide missing.** AIFactory `values.yaml` points at `guides/security/gvisor.md`, which does not exist; the gVisor caveats (no `strict` bwrap mode, no Nix builds under runsc) should live there.

## Remediation plan

Phased, cheapest-and-highest-value first. None of Phase 1 requires the deferred microVM boundary.

**Phase 1 — close the cheap config-baseline gaps (no substrate change).**
- Enforce PodSecurity Admission `restricted` (or `baseline` where root nix lanes require it) on the AIFactory/TFactory task namespaces as a GitOps admission backstop (gap 6).
- Tighten Job egress: introduce an egress proxy or FQDN/CIDR allowlist pinning caches, git remotes, and LLM APIs, replacing `443 -> 0.0.0.0/0` (gap 5).
- Add the missing `guides/security/gvisor.md` and fold the gVisor caveats into the threat model (gap 8).

**Phase 2 — reduce Job privilege and mutable surface.**
- Overlay/read-only warm `/nix/store` for task Jobs, or scheduled `nix store verify --all`; document the trust assumption regardless (gap 4).
- Pursue `readOnlyRootFilesystem` with explicit writable `emptyDir` mounts for `/nix/var` and `$HOME` (gap 2).
- Investigate rootless-nix or a narrower capability set for the TFactory verify lanes to shrink the root add-back list (gap 3).

**Phase 3 — the microVM/syscall boundary (trigger-gated).**
- Hold the documented DEFER (gap 1). Re-open against #274/#270 when a trigger fires: gVisor fixes the Nix builder-init incompatibility (retest recipe preserved in `sandbox-runtime-class.md` s6), the cluster moves off k3d to bare-metal k3s or VM-backed nodes (unlocks Kata for the deploy lane), or a non-Nix per-task Job type appears (can adopt `runtimeClassName` immediately behind the existing `sandbox.gvisor.*` Helm value).
- Establish and record a CIS Kubernetes benchmark baseline for nodes and cluster (gap 7).

## Acceptance criteria

- [x] Every per-task Job pod is covered by a default-deny-ingress NetworkPolicy (AIFactory #812, TFactory #651), enabled by default in production values.
- [x] Per-task Job pods run non-root where the image permits, with `allowPrivilegeEscalation: false`, `capabilities.drop: [ALL]`, and `seccompProfile: RuntimeDefault` pinned in the manifest.
- [x] `automountServiceAccountToken: false` on untrusted Job pods; deploy lane uses a narrowly-scoped, dry-run-only SA.
- [x] Inner bwrap OS sandbox default-on for agent commands, with an escape-test corpus.
- [x] microVM/gVisor suitability for per-task Jobs evaluated with reproducible evidence and an explicit, trigger-gated decision.
- [ ] Job egress restricted to an allowlisted set of destinations (no blanket public 443).
- [ ] PodSecurity Admission enforced on task namespaces as an admission backstop.
- [ ] Warm `/nix/store` cross-task tampering mitigated (read-only mount, verify, or documented trust boundary).
- [ ] `readOnlyRootFilesystem` (with scoped writable mounts) on build/verify Jobs.
- [ ] TFactory verify-lane root privilege reduced or justified in the threat model.
- [ ] CIS Kubernetes / node benchmark baseline established and evidenced.
- [ ] A syscall/VM isolation boundary (gVisor or Kata) on the untrusted-code Jobs — pending a Section-3 re-evaluation trigger.

## Evidence artifacts

- bwrap sandbox: `AIFactory/apps/web-server/server/services/sandbox.py`; escape corpus `AIFactory/tests/test_sandbox_escape_corpus.py`, `AIFactory/tests/test_agent_sandbox.py`.
- Job NetworkPolicies: `AIFactory/charts/aifactory/templates/networkpolicy-tasks.yaml` (#812); `TFactory/charts/tfactory/templates/networkpolicy-jobs.yaml` (#651); defaults in each chart's `values.yaml` (`networkPolicy.enabled: true`).
- Job securityContext: `AIFactory/apps/backend/core/job_dispatch.py`; `TFactory/apps/backend/tools/runners/kube_sandbox.py` (`POD_SECURITY_CONTEXT` / `CONTAINER_SECURITY_CONTEXT`).
- Read-only-rootfs support (non-k8s runners): `AIFactory/apps/backend/core/factory_sandbox.py`; `TFactory/apps/backend/tools/runners/docker_runner.py`.
- gVisor evaluation and compensating-controls checklist: `Factory/docs/security/sandbox-runtime-class.md` (issue #274); CI: `AIFactory/.github/workflows/gvisor-smoke.yml`; toggle in `AIFactory/charts/aifactory/values.yaml` (`sandbox.gvisor.*`).
- Untrusted-content threat model: `Factory/docs/security/untrusted-content-threat-model.md`.
- PodSecurity reference (present only on KEDA ns): `factory-gitops/apps/keda/manifests/namespace.yaml`.
