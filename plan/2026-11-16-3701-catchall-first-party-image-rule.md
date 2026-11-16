---
status: draft
issue: 3701
spec: spec/2026-11-16-3701-catchall-first-party-image-rule.md
coders:
  1: lead   # one 60-line YAML file, copy of an existing rule shape
  2: lead   # test fixtures need the CLI output read back
  3: lead   # small tricky logic in a security checker, reviewed by codex
  4: lead   # prose section, no handoff worth its cost
reviewers:
  - codex   # owner decision 2026-11-16: only Codex as second reviewer
---

# Plan: catch-all first-party image rule (Audit)

Approved spec decisions, carried over. Work in a factory-gitops worktree off
`origin/main` (branch `feat/3701-catchall-first-party-image`), rebase on
`origin/main` before implementing and before the final push.

- New file `apps/kyverno-policies/manifests/report-first-party-image-outside-coverage-groups.yaml`,
  one ClusterPolicy, one rule `first-party-image-in-namespace-with-no-coverage-group`.
  `match.any`: one `resources` clause, `kinds: [Pod]`. `exclude.any`: one
  `resources` clause with `namespaces: [factory, gateway, fides, fides-reporter,
  kube-system, kube-public, kube-node-lease]` and nothing else.
  `validationFailureAction: Audit`, `failurePolicy: Ignore`,
  `webhookTimeoutSeconds: 30`, `background: true`, annotation
  `pod-policies.kyverno.io/autogen-controllers: none`.
- Context `uncovered` = images of containers, initContainers, ephemeralContainers
  filtered by `(?i)^ghcr\.io(:[0-9]+)?/olafkfreund/`, `default: []`;
  precondition `uncovered | length(@) > 0`; `validate.deny: {}` with a message
  naming the images and the fix, pointing at `docs/image-signature-admission.md`.
- Separate file, not a rule in `require-first-party-signature-coverage`.
- Enforce stays off.

## Steps

1. Create the policy file above (copy the context/precondition/validate shape
   from the gateway rule in `require-first-party-signature-coverage.yaml:279-293`;
   header comment short, link the doc).
   Check: `yq . <file>`; step 2 exercises it.
   Traps: a non-literal match shape; `exclude` must hold only `namespaces`.
2. Add `tests/kyverno-test-first-party-outside-coverage.yaml` and
   `tests/resources-first-party-outside-coverage.yaml`. `fail`: first-party in
   container, initContainer, ephemeralContainer, digest-pinned, and a
   `GHCR.IO:443`-style variant, all in a non-covered namespace (e.g.
   `monitoring`). `skip`: third-party image there, and first-party images in
   each of the seven excluded namespaces.
   Check: `kyverno test apps/kyverno-policies/tests -f kyverno-test-first-party-outside-coverage.yaml`
   with CLI v1.18.2, all cases pass; capture whether excluded resources report
   `Excluded` (record the output in the PR).
   Traps: expected `fail` resources must not be `Excluded` (CI #148 gate);
   kyverno CLI panics on some fields, keep resources minimal.
3. Edit `apps/kyverno-policies/assert-signature-lists-agree.py`: add check E
   (`match.any` must be one `resources` clause with `kinds: [Pod]` and no
   namespaces or selectors; strict single exclude clause with literal namespaces only; set equals
   `REQUIRED_NAMESPACES | signature_namespaces | {kube-system, kube-public,
   kube-node-lease}`); mention it in the docstring and success line.
   Check: script green; then red for each of: remove an exclusion, add one,
   add a second exclude clause, add a namespace to `match` (revert each).
   Traps: the script runs from repo root and uses `yq`; run `ruff` if the repo
   lints Python; keep existing messages unchanged.
4. Add a section to `docs/image-signature-admission.md` (before `## Notes`):
   what the policy reports, exclusions and why, how to read PolicyReports for
   it, and the flip-to-Enforce procedure: owner decision after seven consecutive days
   with no `fail` row for this policy across a background scan and the four
   covered namespaces unchanged; the flip PR keeps the offline suite green;
   after the owner syncs it a `kubectl apply --dry-run=server` of a Pod with a
   first-party image in a throwaway namespace must be denied (impossible in
   Audit); rollback is a revert of the flip commit.
   Check: links and policy/rule names match the manifest; `grep -n` the
   names.
   Traps: do not rewrite other sections (another change edits this doc).

## Tests

- `kyverno test` (v1.18.2) on the new suite, and on `tests/` as a whole.
- `python3 apps/kyverno-policies/assert-signature-lists-agree.py` from repo root.
- The repo's yaml/manifest checks in `.github/workflows/manifest-validate.yml`
  that can run offline (yamllint/yq where used).
- `codex review --base origin/main`, max 2 rounds.
- After merge (coordinator/owner, not this PR): the synced ClusterPolicy is
  Ready and its PolicyReport rows are only `skip`.

## Rollback

Revert the PR. Deleting the policy file makes Argo CD prune the ClusterPolicy;
its PolicyReport rows disappear with it. No other component depends on it.
