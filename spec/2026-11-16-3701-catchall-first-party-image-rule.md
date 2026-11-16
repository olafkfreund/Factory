---
status: approved
issue: 3701
intent: intent/2026-11-16-3701-catchall-first-party-image-rule.md
---

# Spec: catch-all first-party image rule (Audit)

All paths are in olafkfreund/factory-gitops unless stated.

## Design

**One new ClusterPolicy file**, `apps/kyverno-policies/manifests/report-first-party-image-outside-coverage-groups.yaml`
(the Argo CD app `kyverno-policies` syncs the whole directory), one rule
`first-party-image-in-namespace-with-no-coverage-group`:

- `match`: `Pod`, all namespaces. `exclude`: `factory`, `gateway`, `fides`,
  `fides-reporter` (they have their own coverage rules) and `kube-system`,
  `kube-public`, `kube-node-lease` (cluster-owned).
- `spec`: `validationFailureAction: Audit`, `failurePolicy: Ignore`,
  `background: true`, annotation `pod-policies.kyverno.io/autogen-controllers: none`,
  copied from the sibling policy for the same reasons (one standing row per Pod,
  no registry call).
- Context `uncovered`: the same jmesPath as the gateway rule without the
  "not covered" filter, because in an uncovered namespace every first-party
  image is uncovered: images of `containers`, `initContainers` and
  `ephemeralContainers` matching `(?i)^ghcr\.io(:[0-9]+)?/olafkfreund/`.
- Precondition `uncovered | length(@) > 0`; `validate.deny: {}` with a message
  naming the images and the fix (give the namespace a coverage group: a
  `verifyImages` rule plus a coverage rule in the sibling policy).

Why a **separate policy file** and not a fifth rule in
`require-first-party-signature-coverage`: `assert-signature-lists-agree.py`
rejects any rule in that file whose `match` is not a literal-namespace list, and
each rule there mirrors exactly the signature globs of its namespaces. A
catch-all has no namespace list and no mirror. A separate file leaves the
checker and the four existing rules untouched.

**Drift guard** in `assert-signature-lists-agree.py`: a short check E reads
the new policy and requires the ONE supported exclusion shape: `match.any` is
a single `resources` clause for `Pod`, `exclude.any` is a single `resources`
clause holding only a literal, wildcard-free `namespaces` list (no selectors,
names, annotations or extra clauses); anything else is an error. Then the
excluded set must equal `REQUIRED_NAMESPACES | signature_namespaces |
{kube-system, kube-public, kube-node-lease}`. A namespace that gains a coverage
group but stays out of the exclude list double-reports; one dropped from
coverage but still excluded would be a silent hole (check D catches the
missing coverage rule, E the stale exclusion).

**Tests**: new suite `apps/kyverno-policies/tests/kyverno-test-first-party-outside-coverage.yaml`
and `resources-first-party-outside-coverage.yaml` (discovered by content in CI,
no workflow edit). `fail`: first-party image in an uncovered namespace (a
container, an initContainer, an ephemeralContainer, a digest-pinned ref, an
uppercase/registry-port variant). `skip`: third-party image in an uncovered
namespace (genuinely evaluated), and first-party images in each of the seven
excluded namespaces (reported `Excluded`, which the CI #148 gate accepts for
`skip`). The `fail` cases prove the rule evaluates.

**Docs**: a new section in `docs/image-signature-admission.md`: what the rule
reports, the exclusions and why, how to read it
(`kubectl get cpol`, `kubectl get polr -A`), and the flip procedure. Flip to
Enforce is the owner's decision after a clean week of PolicyReports: no `fail`
row for this policy for seven consecutive days across a background scan and the
four covered namespaces unchanged. Procedure: the PR that flips
`validationFailureAction` to `Enforce` must keep the offline suite green; after
the owner syncs it, a `kubectl apply --dry-run=server` of a Pod with a
first-party image in a throwaway namespace must be denied (this check is only
possible after the flip, since Audit admits it), and the rollback is a revert
of that commit (or `PANIC.sh` if the owner adds this policy to it). Enforce stays off in this change.

## Alternatives rejected

- Fifth rule in the existing coverage policy: breaks the agree checker's
  match-shape model (above).
- `verifyImages` catch-all with no attestor: yields no standing report row on
  background scans (measured and documented in the sibling policy header).
- Allow-list of namespaces (`namespaces: [list]`): a new namespace would again
  be unchecked, which is the bug.
- Enforce now: nothing has been observed denying here; owner decision.

## Risks

- A future legitimate first-party deployment into a new namespace shows a
  `fail` row: intended, it is the signal; Audit never blocks.
- Report volume: one row per Pod in non-excluded namespaces, mostly `skip`.
  Today ~ the pods of `argocd`, `kyverno`, `keda`, `tailscale`, `default`.
- Excluded list drifting from the coverage groups: guarded by check E.
- `failurePolicy: Ignore`: Kyverno outage admits everything; same as the
  sibling policy.

## Verification

- `kyverno test` with CLI v1.18.2 over the new suite and the existing suites.
- `python3 apps/kyverno-policies/assert-signature-lists-agree.py` green, and
  red when an exclusion is removed, when one is added, and when an extra
  exclude clause is added (each checked once by hand).
- The CLI v1.18.2 output for the excluded-namespace cases is captured once to
  confirm they report `Excluded` and satisfy `skip`; the `fail` cases are what
  prove evaluation.
- Offline lint the repo CI runs (`manifest-validate.yml` steps for yaml and
  kyverno).
- After merge (coordinator/owner): the policy appears Ready, PolicyReports
  for the catch-all show only `skip`.
