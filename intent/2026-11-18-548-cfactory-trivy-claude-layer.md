---
status: approved
issue: 548
author: olafkfreund
---

# Intent: CFactory Trivy image scan and the bundled claude binary

Issue: olafkfreund/CFactory#548 (follow-up to CFactory#540).

## Problem

CFactory#540 raised the Trivy image-scan timeout to 20m after deploy run
44220569439 (main ea31539) failed in the backend image scan. Trivy died while
reading `usr/local/lib/python3.15/site-packages/claude_agent_sdk/_bundled/claude`
(the ~356 MiB uncompressed claude binary inside the `claude-agent-sdk` wheel)
with `stream error: stream ID 17; PROTOCOL_ERROR` after 7m41s.

What the evidence supports, and what it does not:

- The scan is not slow. Backend scan steps of successful runs take 8-12 s
  (deploy runs 44291915848, 44223811886, 44189364641; PR run 44295467707).
- The failure is a transient HTTP/2 transport error. The deploy scan reads the
  image from the registry (`trivy image <ref>@<digest>`, `deploy.yml`), while the
  PR scan reads a locally loaded image. The 20m timeout only lets a stuck
  stream sit longer.
- A `--skip-files` entry would not remove that transfer: Trivy walks the layer
  tar, so the skipped file's bytes are still consumed from the stream (Codex
  review of the first draft, Trivy v0.73.0 `walker/tar.go`). It would also
  remove the one large third-party binary from the vulnerability gate.
- The SDK is declared `claude-agent-sdk>=0.1.16`, so the image ships whatever
  binary PyPI serves that day (0.2.183 one run, 0.2.184 the next). That is a
  supply-chain gap of its own, independent of the scan failure.

## Proposed outcome

- The deploy image scans read the image from the local Docker daemon after a
  retried `docker pull`, not from a raw registry stream. Gate flags unchanged,
  no skips of any kind. Scan timeout back to the Trivy default (5m): the
  measured need is about 12 s.
- The SDK version and the binary's sha256 are pinned in the repo; CI fails on
  a mismatch (PR gate and deploy).
- The existing Syft SBOM + cosign attestation stays the SBOM mechanism.
- Proven by before/after CI timings and a negative test: a planted fixable
  HIGH still fails the gate with the same flags.

## Affected users and systems

CFactory `apps/backend/requirements.txt`, `.github/workflows/{image-build,deploy}.yml`,
a new lock file and verify script, `tests/test_trivy_gates.py`. Maintainers who
bump `claude-agent-sdk` also update one lock file.

## Constraints

- No `--skip-files`, `--skip-dirs`, or `.trivyignore`; no weakening for any path.
- Do not merge; the coordinator merges. No live-cluster changes.

## Open questions

None. Delegated decision (owner delegation 2026-11-18): the issue asked for a
`--skip-files` for the binary. The measurement and the Codex review show that
does not fix the failure and loses coverage, so the least risky option that
meets the issue's goal (no more failed or slow scans, binary tracked) is to fix
image acquisition, keep full scan coverage, and add the pin + checksum check.
