---
status: draft
issue: 548
spec: spec/2026-11-18-548-cfactory-trivy-claude-layer.md
coders:
  2: codex   # contained shell script with several failure paths
  4: codex   # contained test additions, mechanical once steps 1-3 exist
reviewers:
  - codex    # independent read of the final diff against this plan
---

# Plan: CFactory Trivy image scan and the bundled claude binary

Repo olafkfreund/CFactory, branch `fix/548-trivy-claude-layer` off `dev`.
Approved decisions (spec): do NOT add `--skip-files`/`--skip-dirs`/`.trivyignore`;
fix image acquisition in deploy (docker pull with retries, scan with
`--image-src docker --timeout 5m`); pin `claude-agent-sdk==0.2.184` and the
binary sha256 in `apps/backend/claude-bundle.lock`; verify both in CI; tie the
existing Syft CycloneDX SBOM to the pin; keep Syft + cosign as the only SBOM
mechanism. Measured: 0.2.184, 372904464 bytes, sha256
`343c744baa14bfd38286a7cb90871051f04379956da6c5b803a9e66019a76ac9`, path in
image `/usr/local/lib/python3.15/site-packages/claude_agent_sdk/_bundled/claude`
(resolve via `claude_agent_sdk.__file__`, the python minor changes).

## Steps

1. `apps/backend/requirements.txt:25`: `claude-agent-sdk>=0.1.16` -> `==0.2.184`
   with a one-line comment pointing at the lock. New
   `apps/backend/claude-bundle.lock` (lines `version=0.2.184`,
   `sha256=<above>`, `platform=linux/amd64`, header comment: bump both files
   together). -> verify by `grep -n claude-agent-sdk apps/backend/requirements.txt`.
   Traps: AIFactory-style generated files do not apply; keep the lock key=value
   so the script can parse it with no extra deps.
2. (codex) New `.github/scripts/verify-claude-bundle.sh <image>` (bash,
   `set -euo pipefail`, executable). Reads the lock; runs
   `docker run --rm --entrypoint python <image> -c ...` printing arch-independent
   `version` and `sha256` of `claude_agent_sdk/_bundled/claude` (via
   `claude_agent_sdk.__file__`); fails with a message naming
   `claude-bundle.lock` and `requirements.txt` on any mismatch, missing/malformed
   lock, docker failure, or non-amd64 image (`docker image inspect -f
   '{{.Architecture}}'`). No secrets, no network. -> verify by step 4 tests.
   Traps: match the style of `.github/scripts/assert-signature-location.sh`.
3. `.github/workflows/image-build.yml` and `deploy.yml`:
   - image-build: add `--timeout 5m` to the two `trivy image` commands; add a
     step "Verify claude bundle pin" running the script on `${BACKEND_TAG}`
     right after the backend smoke step.
   - deploy: replace `--timeout 20m` with `--timeout 5m --image-src docker`; add
     a step before the scans that does `docker pull` of
     `${BACKEND_IMAGE}@<digest>` and `${FRONTEND_IMAGE}@<digest>` with 3 attempts
     each; add "Verify claude bundle pin" on the backend digest after the pull and
     before the Trivy scan, so it precedes `cosign sign`; after Syft writes
     `sbom-backend.cyclonedx.json`, add a `jq -e` assertion that a component named
     `claude-agent-sdk` has the locked version. Keep every severity flag.
   -> verify by `python -c yaml.safe_load` of both files, `actionlint` if present.
   Traps: `tests/test_trivy_gates.py` tokenises only lines starting `trivy `
   (keep `trivy image ...` flags on one logical line). Action SHAs stay pinned.
4. (codex) `tests/test_trivy_gates.py` additions and new
   `tests/test_verify_claude_bundle.py` as listed in the spec (no skip flags,
   `--timeout` on image scans, `--image-src docker` in deploy, exact pin equals
   lock, verify step present and before cosign sign in deploy, stub-`docker`
   cases: match, wrong sha, wrong version, missing lock, malformed lock, docker
   failure). -> verify by `python -m pytest tests/test_trivy_gates.py
   tests/test_verify_claude_bundle.py -q`.
   Traps: repo ruff config (`ruff.toml`); keep tests offline.
5. Evidence (lead): rebuild backend image, run the verify script green; red with
   an edited lock; run trivy negative test (`urllib3==1.26.4` fixture, JSON
   shows the advisory) and clean-image control; collect CI before/after timings.

## Tests

`python -m pytest tests -q -k "trivy or claude_bundle"`; `ruff check`,
`ruff format --check` on touched files; yaml parse of both workflows; CI green
on the PR head SHA.

## Rollback

Revert the PR. The only runtime effect is CI/deploy; the pin changes the image
only by fixing the SDK at the version it already resolves to today.
