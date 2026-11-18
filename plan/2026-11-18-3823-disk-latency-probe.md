---
status: draft
issue: 3823
spec: spec/2026-11-18-3823-disk-latency-probe.md
coders:
  1: codex   # small tricky logic (counter deltas, bounds), contained to one embedded script
  2: me      # manifest deletion + header
  3: me      # runbook prose
reviewers:
  - codex
---

# Plan: disk latency probe in restart-watchdog; retire agent netpol probe

Decisions carried from the approved spec (repo: olafkfreund/factory-gitops,
worktree branch `feat/3823-disk-latency-probe`, base `main`):

- Read `/proc/diskstats` inside the watchdog pod (kernel-wide; no hostPath, no
  privilege). Two reads, measured monotonic elapsed time, interval bounded
  1..30 s (default 5); bad config => `unavailable`, never raises, never delays
  or blocks notification beyond the interval.
- Record schema `disk_probe/v1`: `schema, ts, device, interval_s, status
  (ok|no_io|unavailable), await_ms, util_pct, ios, error`. One `DISKPROBE <json>`
  stderr line per run and a `## Node disk at observation time` section in every
  issue body (open/reopen/escalate/renotify). Await is read+write only
  (flush/discard excluded); say so in the section.
- Flags: `DISK_PROBE=observe|off` (default observe, set in CronJob env),
  `DISK_DEVICE=sdd`, `DISK_INTERVAL_SECONDS=5`.
- Delete CronJob `netpol-node-probe-agent`; update file header and runbook.

## Steps

1. `apps/restart-watchdog/manifests/manifests.yaml`, embedded watchdog.py
   (ConfigMap `restart-watchdog-script`, 4-space indented block): add
   `import math, time`; `parse_diskstats`, `disk_metrics`, `disk_probe`,
   `disk_section(sample)`; extend `issue_body` to append the section when
   `record.get("disk")` is set; in `main()` take one sample before `notify`
   when `DISK_PROBE != off` (inside try/except), print `DISKPROBE`, attach
   `r["disk"]` to each record; add the selftest assertions listed in the spec.
   Add env `DISK_PROBE=observe`, `DISK_DEVICE=sdd`,
   `DISK_INTERVAL_SECONDS="5"` to the CronJob. Update the file header comment
   with a short DISK PROBE paragraph (the "does not emit to OpenObserve" text
   stays true).
   -> verify: `python3 .github/scripts/extract_embedded_script.py
   apps/restart-watchdog/manifests/manifests.yaml watchdog.py /tmp/w.py &&
   python3 /tmp/w.py selftest` prints `selftest OK`; `python3 -c "import yaml;
   list(yaml.safe_load_all(open(...)))"`.
   Traps: block scalar indentation (4 spaces under `watchdog.py: |`); stdlib
   only; no `except:` without `noqa: BLE001` comment style used in file; no
   secrets in output; keep exit codes unchanged.
2. `apps/netpol-node-probe/manifests/manifests.yaml`: delete the
   `netpol-node-probe-agent` CronJob (and its `---`), rewrite the header lines
   1-8 "One CronJob per node" to say server only, agent retired while
   agent-0 carries `rfactory.io/desktops` (Kyverno `rfactory-desktops-toleration`
   admits the toleration only on desktop launchers), and fix the failure-mode
   comment that mentions hard-coded node names. -> verify: `kubectl kustomize
   apps/netpol-node-probe/manifests | grep -c 'kind: CronJob'` is 1.
   Traps: `application.yaml` unchanged; the ConfigMap script stays shared.
3. `docs/runbooks/k3d-restart.md`: lines 79-83 and 87-98: only the server
   CronJob exists; agent-0 is checked by the manual rule-count steps; how to
   re-add the agent CronJob if the taint is removed (copy from git history,
   `git show <this commit>^:apps/netpol-node-probe/manifests/manifests.yaml`).
   -> verify: read; `grep -n "netpol-node-probe-agent" docs` only in the
   historical/re-add context.
4. Lead (not a coder step): full selftests for job-watchdog workflow
   (`job-watchdog-test.yml` commands), manifest YAML parse, codex
   `review --base origin/main`, PR, checks. Comments on Factory#3823 and
   #3832 with decisions and owner actions.

## Tests

- restart-watchdog selftest as in step 1 (also the other three embedded
  selftests in `.github/workflows/job-watchdog-test.yml` still pass).
- `pytest .github/scripts -q` (extractor test must still find all programs).
- `kubectl kustomize` for both apps renders.

## Rollback

Revert the PR: Argo restores the agent CronJob (which fails as before while the
taint exists) and removes the probe. The probe flag `DISK_PROBE=off` disables
sampling without a revert.
