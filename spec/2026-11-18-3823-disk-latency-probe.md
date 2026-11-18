---
status: draft
issue: 3823
intent: intent/2026-11-18-3823-disk-latency-probe.md
---

# Spec: disk latency probe in restart-watchdog; retire the agent netpol probe

## Design

### A. Disk probe (factory-gitops `apps/restart-watchdog`)

`/proc/diskstats` is kernel-wide, not per-namespace. Verified read-only:
`docker exec k3d-factory-agent-0 grep sdd /proc/diskstats` and the same on
server-0 both list `sdd`, so a plain pod reads the host SSD counters with no
hostPath, no privilege, no new volume. (Pod uid 65532 and a read-only root FS
are unaffected: procfs is world-readable.)

New code in the embedded `watchdog.py`, all stdlib:

- `parse_diskstats(text) -> {dev: (reads, read_ms, writes, write_ms, io_ms)}`
  from fields 4, 7, 8, 11 and 13 of each line (1-based after major/minor/name
  are counted as 1-3).
- `disk_metrics(a, b, interval_s, device, ts)` computes over the delta:
  `await_ms = (d_read_ms + d_write_ms) / (d_reads + d_writes)`,
  `util_pct = min(100, d_io_ms / (interval_s*1000) * 100)`.
- `disk_probe(device, interval_s)` reads twice, `interval_s` apart, and divides
  by the measured monotonic elapsed time (recorded as `interval_s`), not the
  requested sleep. Configuration is parsed inside the same try block: a
  non-numeric, non-finite or out-of-range (not 1..30 s) `DISK_INTERVAL_SECONDS`
  yields `status: "unavailable"` with a short `error`. It never raises.
- Stable record (schema `disk_probe/v1`), one JSON line per run on stderr
  prefixed `DISKPROBE `:

  ```
  {"schema":"disk_probe/v1","ts":"<UTC iso>","device":"sdd","interval_s":5.0,
   "status":"ok|no_io|unavailable","await_ms":<float|null>,"util_pct":<float|null>,
   "ios":<int|null>,"error":<str|null>}
  ```

  `await_ms` is mean read+write await; flushes and discards are counted
  separately by the kernel and are excluded (relevant to SQLite fsync latency,
  so a healthy value does not exonerate the disk). `util_pct` is kernel
  io_ticks and does not prove saturation. `no_io` = zero completed reads and
  writes in the interval (await undefined, util still
  reported). Counter wrap/regression (negative delta) is `unavailable`.
- Every issue body, opened, reopened, escalated or renotified, gets a
  `## Node disk at observation time` section with the same fields and the
  caveat that the sample is taken at watchdog run time, not at the restart.
- Flag `DISK_PROBE` = `observe` (default, set explicitly in the CronJob) or
  `off`; `DISK_DEVICE` default `sdd`; `DISK_INTERVAL_SECONDS` default 5.
  Probe failure never changes the exit code, suppresses or delays an alert.
  The sample runs once per run, before notifying, and delays
  notification by at most the bounded interval (<= 30 s, default 5 s).

Recording: the log line (readable from the 3 retained successful Jobs; no log
collector is deployed, so it is not durable) plus the issue text (durable).
That is why restart-watchdog and not job-watchdog: the restart events live
here, and job-watchdog's `job_health` stream is per CronJob. No OpenObserve
credentials are added (the file header's reasoning for not emitting stays).

Limit, stated in the issue text: a 30-minute cadence cannot observe a stall
that lasts seconds. The probe builds a baseline and catches a sustained
degradation; confirming the hypothesis still needs the owner's `iostat`.

### B. Netpol probe (#3832)

Evidence (read-only, 2026-11-18): Jobs `netpol-node-probe-agent-*` fail with
`DeadlineExceeded` (420 s); the pod is Pending with `FailedScheduling: 1
node(s) had untolerated taint(s)`; agent-0 has taint
`rfactory.io/desktops=true:NoSchedule`; Kyverno ClusterPolicy
`rfactory-desktops-toleration` (Enforce, owned by RFactory) rejects that
toleration on any pod outside `rfactory-desktops` desktop launchers. Both
nodes are Ready, no pressure; the server probe passes every 10 min. The last
agent success was before the taint was applied. This is a probe that can no
longer be scheduled, not evidence of lost enforcement, and not a disk-stall
effect.

Decision: delete the `netpol-node-probe-agent` CronJob (Argo prunes it) and
fix the file header and `docs/runbooks/k3d-restart.md`: the agent probe is
retired while agent-0 is tainted for desktops; the manual rule-count check in
the runbook covers agent-0 after a restart; re-add the CronJob if the taint is
removed. job-watchdog closes its issue when the CronJob is gone.

## Alternatives rejected

- hostPath `/proc` mount: unnecessary, the pod already sees kernel-wide
  diskstats.
- Emit to OpenObserve from restart-watchdog: needs credentials and a stream;
  the header deliberately avoids it.
- Add a probe-specific toleration to the netpol probe, or loosen the Kyverno
  policy: changes a security boundary owned by another repo.
- Suspend the agent CronJob: leaves a permanent job-watchdog "suspended"
  warning.
- Node-affinity the agent probe off agent-0: it would then test server-0
  twice.

## Risks

- Delete leaves no sentinel on agent-0 (it hosts desktop VMs only). Mitigated
  by the runbook manual check; accepted.
- ~5 s extra runtime per run; the Job has no tight deadline. Memory/CPU are
  negligible.
- Sampling host-wide disk shows correlation only.

## Verification

- Selftest in the embedded script (cluster-free): `parse_diskstats` on real
  lines, `disk_metrics` for ok / no_io / negative delta / missing device,
  `disk_probe` with an injected reader that raises, issue body contains the
  section only when a sample is present, `DISK_PROBE=off` yields no sample, an overslept interval (elapsed 10 s for a
  5 s request) is divided by 10, a bad `DISK_INTERVAL_SECONDS` gives
  `unavailable` and notification still runs.
  Run in CI by `job-watchdog-test.yml` (extract + `selftest`).
- `python3 .github/scripts/extract_embedded_script.py ... && python3 x.py selftest`.
- manifest-validate CI green; `kubectl kustomize apps/netpol-node-probe/manifests`
  renders only the server CronJob.
- After merge (owner/coordinator): the next restart-watchdog pod's log shows a
  `DISKPROBE` line with `status` `ok` or `no_io` and `device` `sdd`; the node
  check above does not itself prove the pod's procfs view.
