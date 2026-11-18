---
status: draft
issue: 548
author: olafkfreund
---

# Intent: CFactory Trivy image scan and the bundled claude binary

Issue: olafkfreund/CFactory#548 (follow-up to CFactory#540).

## Problem

CFactory#540 raised the Trivy image-scan timeout to 20m after deploy run
44220569439 (main ea31539) failed in the backend image scan. The failing file
was `usr/local/lib/python3.15/site-packages/claude_agent_sdk/_bundled/claude`,
the ~200 MB claude binary that the `claude-agent-sdk` wheel bundles
(`apps/backend/requirements.txt` has it unpinned: `>=0.1.16`). The error was a
registry stream error (`stream ID 17; PROTOCOL_ERROR`) after 7m41s.

The issue title says the scan is slow. The data says otherwise: successful
scans of the same layer take 8-12 s (deploy runs 44291915848, 44223811886,
44189364641; PR run 44295467707). One failure in the last 30 deploy runs. The 20m
timeout only lets a stuck stream sit longer. Meanwhile that one binary is both
the only thing that trips the scan and the one thing in the image with no
version or checksum pin: a floating `>=` SDK ships whatever binary PyPI
serves that day.

## Proposed outcome

- The Trivy image scans no longer read that one file through the registry
  stream; every other path (OS packages, python and node deps) stays under the
  same HIGH/CRITICAL, fixable-only gate.
- The binary is covered by a separate check instead: SDK version and the
  binary's sha256 are pinned in the repo, CI fails on a mismatch, and the
  extracted binary is scanned by `trivy fs` with the same gate.
- The existing Syft SBOM + cosign attestation in `deploy.yml` stays the SBOM
  mechanism (no new one).
- Trivy timeout goes back near the measured need, with headroom.
- Proven by before/after CI timings and a negative test: a planted fixable HIGH
  outside the skipped path still fails the gate.

## Affected users and systems

CFactory `Dockerfile`, `apps/backend/requirements.txt`,
`.github/workflows/{image-build,deploy}.yml`, `tests/test_trivy_gates.py`.
Maintainers who bump `claude-agent-sdk` now also update one lock file.

## Constraints

- No blanket `.trivyignore`; no weakening of the gate for any other path.
- Do not merge; coordinator merges. No live-cluster changes.
- A skip must not leave the binary unwatched: the replacement check ships in
  the same PR.

## Open questions

None. Delegated decisions (owner delegation 2026-11-18): scope the skip to the
exact SDK path rather than a broader glob; reuse the existing Syft/cosign steps
for the SBOM; treat "slow scan" as "fragile registry stream" since the
measurement shows the former is false.
