---
status: draft
issue: 3814
spec: spec/2026-11-18-3814-fleet-match-tfactory-blind.md
coders:
  1: codex   # small tricky logic: retry classification in gh()
  2: claude  # contained test edit next to existing selftest cases
reviewers:
  - codex
---

# Plan: retry transient GitHub reads in fleet-match

Approved decisions (spec): retry GET only, 3 attempts, 2s/5s waits, on
URLError/timeout, 5xx, 429, rate-limited 403; never retry other 4xx or
non-GET; one job-wide \`RETRY_DEADLINE\` of 120s, honour \`Retry-After\` (<=30s, within budget); log HTTP code and body[:200] on a final failure; `runs=None` stays
`unevaluable`. Code lives in factory-gitops
`apps/fleet-match/manifests/manifests.yaml` (Python in a ConfigMap, 4-space
YAML block indent). Artifacts live in Factory; the code PR is in factory-gitops.

## Steps

1. `gh()` (~line 652): wrap `urlopen` in a loop for `method == "GET"` per the
   decisions above; add `import time`; make the sleeps a module constant
   `RETRY_WAITS = (2, 5)` so the selftest can zero them. In `repo_state()`
   (~line 1033) log `HTTPError` as `HTTP code + body[:200]` (no headers).
   → verify by step 2.
   Traps: keep the 4-space block indent; never log the Authorization header.
2. `_selftest()` (~line 1324 next to `littered`): add the three cases from the
   spec (502,502,ok succeeds; 404 raises after one call; `runs=None` for a
   repo target is `unevaluable`) → verify with the extract + selftest command.
   Traps: monkeypatch `urllib.request.urlopen` and `RETRY_WAITS`, restore after.

## Tests

`python3 .github/scripts/extract_embedded_script.py apps/fleet-match/manifests/manifests.yaml match.py /tmp/fm.py && python3 /tmp/fm.py selftest` prints `selftest OK`;
with step 1 reverted the new cases fail. Also run `yamllint`/manifest-validate as CI does.

## Rollback

Revert the commit; ArgoCD resyncs the ConfigMap.
