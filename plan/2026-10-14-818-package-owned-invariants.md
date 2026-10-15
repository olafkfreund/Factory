---
status: draft
issue: 818
spec: spec/2026-10-14-818-package-owned-invariants.md
---

# Plan: RFC-0024, package-owned runtime invariants

This task is docs only, in the Factory hub, on branch
`docs/818-package-owned-invariants`. The session implements it itself, since
it edits two files and needs no coder handoff.

## Approved decisions to carry into the RFC

- **Scope.** Adopt per service, with full coverage within each service.
  PFactory goes first. The next service starts only after PFactory has full
  coverage and has run one release with the checks on in production. The
  order after PFactory is CFactory, then TFactory, then AIFactory.
- **Unit of coverage.** The top-level package: any directory with an
  `__init__.py` under the service's declared source roots. Each package gets
  one companion, `<pkg>/_invariants.py`, which registers at least one check
  or one written reason.
- **Discovery.** The checker finds packages on disk and no longer reads the
  hand-written `COVERED` tuple. A source root with no packages is an error.
- **Vendored packages.** `factory_common` keeps its sibling-file companion.
  These exceptions go in a small, explicit map, and every entry must exist.
- **Guards that stay.**
  - `_PLACEHOLDER` and `_EMPTY_REASON_MIN_WORDS`.
  - A duplicate registration is rejected.
  - A stale declaration fails.
- **Production.**
  - Add `/api/ready`, which returns 503 when a critical check fails. Results
    are cached for one probe period.
  - Only the readiness probe moves to `/api/ready`. Liveness stays on
    `/api/health`, because PFactory's two probes both use `/api/health` today
    (factory-gitops `apps/pfactory/manifests/manifests.yaml:425-426`).
  - `register(..., critical=False)` is how an owner opts a check in.
  - Non-critical checks run on a timer, default 5 minutes. A violation logs
    at error level and increments
    `factory_invariant_violations_total{service,package}`.
  - `FACTORY_INVARIANTS` is on by default, and `=0` turns it off. The
    allowlist and blocklist stay.
  - A check runs non-critical for one release first, and is promoted only if
    it produced no false positive in that release.
  - Critical checks make no network calls.
- **Relation to other checks.**
  - RFC-0006 VAL levels grade the output a factory produced for a task. They
    don't overlap with this RFC, so the two get cross-links in both
    directions.
  - `check_gate_liveness.py` and `check_test_collection.py` are the CI-side
    half of the same idea and are left unchanged.
- **No shared library.** Each service keeps its own copy of the roughly
  180-line registry.
- **Measured counts** (`origin/dev`, 2026-10-15):

  | Repo | Top-level packages | Notes |
  | --- | --- | --- |
  | PFactory | 32 | 30 under `apps/backend` and 2 under `apps/web-server`; 560 non-test backend modules; 3 covered |
  | TFactory | 29 | |
  | AIFactory | 28 | |
  | CFactory | 3 | |

- **Rejected alternatives:**
  - per-module coverage;
  - adopting across the whole fleet at once;
  - retiring the pilot;
  - failing `/api/health`;
  - stopping startup on every violation;
  - a vendored shared package.

## Steps

1. `docs/rfc/0024-package-owned-runtime-invariants.md` (new): write the RFC.
   - Follow 0023's front matter: `layout`, `title`, `permalink:
     /rfc/package-owned-runtime-invariants/`, plus the status line with
     Proposed, Created 2026-10-15, Owner, Extends and Affects.
   - Sections:
     1. Problem, citing #818's 11 cases.
     2. Decision.
     3. Design, covering the coverage unit, discovery, production and
        promotion.
     4. Relation to RFC-0006 and the gate checks.
     5. Rollout and cost.
     6. Alternatives rejected.
     7. Risks.
     8. Follow-up issues.
     9. Appendix: the measurement commands.

   Verify by rerunning each appendix command against each repo's
   `origin/dev` and checking that every count matches.
   Traps:
   - Run the commands with `git ls-tree` in the main clones. Never switch
     branches there.
   - Use no hostnames or IP addresses.
2. `docs/rfc/0006-*.md`, in its header block: add one "See also: RFC-0024"
   line explaining why the two differ. Verify by reading `git diff` and
   checking it adds one line only.
3. File the follow-up issues with `gh issue create`, then put their numbers
   into the RFC's follow-up section in the same commit as steps 1 and 2.
   - PFactory:
     - (a) a package-discovery checker, plus companions for every package;
     - (b) `critical`, `/api/ready`, the timer and the metric.
   - factory-gitops: (c) move PFactory's readiness probe to `/api/ready`.
     It depends on (b) being deployed.
   - Hub, filed in the Factory repo: (d) a `rejected/` design record (the
     side idea in #818).

   CFactory, TFactory and AIFactory get no issues yet. The RFC says they
   are filed when the gate in the Scope decision opens.

   Verify that `gh issue view` shows each issue open.
   Traps:
   - In commit messages, use `git commit -F - <<'MSG'`, never backticks.
4. Open a PR to `main` that links the intent, spec and plan, and says the
   session did every step.
   - Merge once CI is green: approval was given in the intent decisions.
     Use `gh pr merge --squash`, never `--admin`.
   - Check that `state == MERGED` before deleting the branch.
   - Comment on #818 with a link to the RFC.

## Tests

- Every count in the appendix is rerun and matches.
- `git diff --stat origin/main` shows only `intent/`, `spec/`, `plan/`,
  `docs/rfc/0024-*` and one line in `docs/rfc/0006-*`.
- The PR's required checks are green.

## Rollback

Revert the squash commit. No runtime is affected. Close the follow-up issues
as not planned if the RFC is withdrawn.
