---
status: approved
issue: 548
intent: intent/2026-11-18-548-cfactory-trivy-claude-layer.md
---

# Spec: CFactory Trivy image scan and the bundled claude binary

## Design

Repo: olafkfreund/CFactory, base `dev`. Four contained changes.

1. **Scan a local image in deploy.** `deploy.yml` "Trivy scan backend image" and
   "frontend image" steps today run `trivy image <ref>@<digest>`, which streams
   layers from ghcr.io. Add one step before them that runs
   `docker pull` on both digests with up to 3 attempts (Docker retries layer
   downloads itself), then scan with `--image-src docker --timeout 5m` plus the
   existing `--severity HIGH,CRITICAL --ignore-unfixed --exit-code 1`.
   `--image-src docker` makes a missing local image a loud failure instead of a
   silent fallback to the registry. The PR gate (`image-build.yml`) already
   scans a locally loaded image, so it only gets `--timeout 5m` for parity.
   Measured need is 8-12 s; 5m is the Trivy default and keeps 25x headroom.
2. **Pin the SDK and its binary.** `requirements.txt`: `claude-agent-sdk==0.2.184`.
   New `apps/backend/claude-bundle.lock` holds `version=` and `sha256=` of
   `claude_agent_sdk/_bundled/claude` (linux x86-64, the only platform the image
   builds: `platforms: linux/amd64`). Measured on the current dev image:
   0.2.184, 372904464 bytes,
   `343c744baa14bfd38286a7cb90871051f04379956da6c5b803a9e66019a76ac9`.
3. **Verify the pin in CI.** New `.github/scripts/verify-claude-bundle.sh <image>`
   runs a short `python` one-liner in the image (`docker run --entrypoint python`)
   printing `importlib.metadata.version` and the sha256 of the bundled binary,
   compares both with the lock, and exits 1 with a clear message on any mismatch,
   missing/malformed lock, missing binary, docker failure, or non-amd64 image
   (`set -euo pipefail`; no `|| true`). Placement: `image-build.yml` runs it on the
   backend build tag right after the build; `deploy.yml` runs it on the pulled
   backend digest, before signing/promotion, as a plain step so its failure stops
   the job. Two separate statements, not one: the binary checksum is checked by
   this script; the SBOM is the existing Syft dual SBOM + `cosign attest`
   (image-digest subject). To tie them, `deploy.yml` also asserts, right after
   Syft writes `sbom-backend.cyclonedx.json`, that its components contain
   `claude-agent-sdk` at the locked version (`jq -e`), so the attested SBOM and the
   pin cannot drift apart. No new SBOM mechanism.
4. **Test.** `tests/test_trivy_gates.py` gains: no trivy command in either
   workflow carries `--skip-files`, `--skip-dirs` or `--ignorefile`; every image
   scan carries `--timeout`; deploy image scans carry `--image-src docker`;
   `requirements.txt` pins `claude-agent-sdk` exactly and the version equals
   `claude-bundle.lock`'s; the verify step exists in both workflows, targets the
   backend tag / digest, and precedes the cosign sign step in `deploy.yml`. A
   new `tests/test_verify_claude_bundle.py` runs the script against a stub
   `docker` on PATH to cover: match, wrong sha, wrong version, missing lock,
   malformed lock, docker failure.

## Alternatives rejected

- **`trivy image --skip-files <claude path>`** (the issue's proposal). Trivy
  walks the layer tar, so the skipped file's bytes are still read from the
  stream and the same PROTOCOL_ERROR can recur (Codex review, Trivy v0.73.0).
  It also removes a 356 MiB third-party binary from the gate. Rejected as
  neither fixing the failure nor keeping coverage.
- **Blanket `.trivyignore` / skip-dirs.** Forbidden by the issue.
- **Retry the whole Trivy step.** Hides the cause and re-streams 356 MiB from
  ghcr.io each attempt; `docker pull` retries per layer.
- **Scan only a local `load: true` build in deploy.** The deploy workflow pushes
  the exact digest that gets signed; scanning a rebuilt copy is not scanning that
  digest. Pulling the digest scans the real artefact.
- **Hash-pinning all of requirements.txt (`--require-hashes`).** Right idea,
  much larger change; out of scope for this issue.

## Risks

- A future SDK bump fails CI until `claude-bundle.lock` and the pin move
  together. Intended; the failure message names both files.
- Pulling two images on the deploy runner costs network, disk and time: the
  buildx `docker-container` builder keeps its cache outside the Docker image
  store, so the pull is cold. Measured and reported in the PR (pull + verify +
  scan, not scan alone).
- Multi-arch: the lock is x86-64 only. Documented in the lock header; the
  script fails if the image arch differs.
- `docker pull` could also hit the stream error; retries absorb a transient one,
  and a persistent registry failure fails loudly before scanning.

## Verification

- Before/after timings from CI: backend Trivy step 8-12 s on `dev` today
  (runs above); after, the PR run and a deploy-equivalent run, both reported
  in the PR.
- Negative test, run locally with the same flags: build a small image that
  installs `urllib3==1.26.4` (known fixable HIGH advisories) and scan it with
  `trivy image --image-src docker --severity HIGH,CRITICAL --ignore-unfixed
  --exit-code 1 --format json`. Pass only if exit is 1 AND the JSON lists
  `urllib3` 1.26.4 with a HIGH/CRITICAL advisory and a FixedVersion; a missing
  image or DB failure would not show that. The clean backend image exits 0 with
  an empty result list.
- Negative test for the pin check: run the script against the backend image with
  an edited lock (wrong sha256, wrong version) and see exit 1; the real lock
  exits 0.
- `pytest tests/test_trivy_gates.py`, `ruff`, `actionlint` / yaml parse for the
  two workflows.
