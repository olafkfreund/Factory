# Signed commits and segregation of duties

> Factory#316 (gap under the #310 compliance program)
>
> This is the **rollout runbook**. The policy and gap analysis for the same domain
> is [`policies/change-management-sod.md`](policies/change-management-sod.md); it
> states what is required and what is missing, this states how to turn it on.

Two controls that branch protection alone does not give us:

1. **Signed commits** — every commit on a protected `main` must carry a verified
   cryptographic signature, so authorship cannot be forged. Today
   `required_signatures` is `false` on every repo in the fleet, including the
   unsigned `github-actions[bot]` commit the gitops CD bot pushes to
   `factory-gitops` main.
2. **Segregation of duties (SoD) / four-eyes** — a change must be authored by one
   person and approved by a second, distinct person before it merges. The Fides
   `change-gate` + `fides approve` flow enforces this and is currently invoked by
   zero workflows.

Branch protection (PR + review + status checks) is already applied fleet-wide via
`scripts/apply_branch_protection.sh` (see `branch-protection.md`). This document
covers the two remaining pieces and the order to roll them out **without breaking
the deploy automation**.

## What ships in this change

- `scripts/apply_branch_protection.sh --signatures` — opt-in, dry-run-by-default
  toggle that enables GitHub `required_signatures` per repo. It prints a per-repo
  **signer pre-flight checklist** and only writes on `--apply`. It is deliberately
  separate from the baseline protection object so signing is rolled out on its own
  schedule.
- This document — the rollout plan and the control mapping.

## What does NOT ship yet: the SoD half

The signing half above is self-contained and needs no external service. The SoD
half does, and it is **not** in this change:

`.github/workflows/fides-change-gate.yml` records a run as a Fides change (trail)
and evaluates `fides change-gate`. It **exists and works** — it is simply not
wired to `pull_request`.

Both original blockers are cleared (Factory#541):

1. ~~The three settings do not exist~~ — provisioned. Flow `Factory`
   (`41184b3e-97ec-4e0d-8461-0a8832530c1f`), service account `factory-ci` with
   role **Writer**, one active key on a 365-day expiry, and the repo carries
   secrets `FIDES_SERVER_URL` / `FIDES_API_TOKEN` and variable `FIDES_FLOW_ID`.
2. ~~The CLI install path 404s~~ — `scripts/fides_gate_preflight.sh` installs a
   pinned, digest-verified release from GitHub instead of piping an installer
   from the server, and asserts the binary is runnable.

Proven end to end on a real runner: preflight passed, a trail was recorded, and
the gate returned its verdict.

**What keeps it off `pull_request` is different and is not a bug.** The gate
HOLDs until `four_eyes` is satisfied, and that needs two *distinct* humans.
Factory is a single-maintainer repo, so no action by one person clears it. On a
PR trigger the check would be red forever — the Factory#484 shape, where an
unsatisfiable review requirement turned every merge into an `--admin` bypass and
produced *less* enforcement. A permanently-red non-required check is worse than
an absent one: it trains people to ignore red. Tracked in **Factory#660**, which
is the real gate to making this a PR check.

Reachability was never among the blockers, contrary to how #541 was originally
written.
`svc/fides-server` is a ClusterIP, but the cluster publishes it through the
existing cloudflared tunnel at `https://fides.freundcloud.org.uk`, which
Cloudflare terminates TLS for. Measured 2026-08-10 from outside the cluster:
`/` 200, `/healthz` 200, `/api/v1/health` 401 (live and auth-gated),
`/cli/install.sh` 404. No Ingress and no cert-manager are needed — the fleet has
neither, and exposes every portal this same way.

It is recorded as absent rather than merged-and-red on purpose. A required check
that can never pass blocks every PR; a non-required check that is permanently red
trains everyone to ignore a red check. Neither is worth having before the server
is reachable — and a gate that soft-passed when unconfigured would be the exact
false-green shape Factory#642 catalogues. Tracked in Factory#541.

Nothing here changes live repo settings. Enabling signing is a deliberate,
per-repo `--apply` decision made after the pre-flight below.

## Why signing breaks automation if enabled blindly

`required_signatures` rejects the next **unsigned** push to `main` from **any**
identity — humans and bots alike. So every identity that writes to a protected
`main` must have signing configured first:

| Repo | Writers to main | Pre-flight |
|---|---|---|
| CFactory, PFactory, TFactory, AIFactory | PARR auto-merge bot (`gh pr merge` with an admin token) | GitHub signs merge/squash commits server-side when the merge is done through the API, so an auto-merge lands signed. Confirm the loop uses merge/squash (not a pushed fast-forward). |
| Factory | Human maintainers only (no direct-to-main automation) | Every maintainer must have verified GPG/SSH signing configured. |
| factory-gitops | `github-actions[bot]` CD bump via `GITOPS_PAT` — **pushes unsigned commits** | Enable LAST, and only after the CD job signs. Either import a bot GPG/SSH signing key into the workflow (`git config user.signingkey`; `commit.gpgsign true`) or move the bump to the GitHub Contents API (server-signed). Enabling before that **freezes all deploys.** |

## Rollout order

Signing and SoD are independent; do signing first (it is the lower-risk half).

### Phase A — enable signing on humans

1. Every maintainer configures verified commit signing (GPG or SSH) on their
   GitHub account and local git (`commit.gpgsign true`). Confirm the "Verified"
   badge appears on their recent commits.
2. Flip `required_signatures` on the low-risk, human-only / API-merged repos
   first, one at a time, dry-run then apply:

   ```
   scripts/apply_branch_protection.sh --signatures --repo Factory        # dry-run
   scripts/apply_branch_protection.sh --signatures --apply --repo Factory
   ```

   Then CFactory, PFactory, TFactory, AIFactory — after confirming the PARR
   auto-merge loop still lands a green PR on each (its merge commit must show as
   Verified).

### Phase B — set up bot signing, then gitops last

3. Configure signing for the `factory-gitops` CD bump (bot signing key in the
   workflow, or Contents-API bump). Land a test bump and confirm it shows as
   Verified.
4. Only then enable signing on `factory-gitops`:

   ```
   scripts/apply_branch_protection.sh --signatures --apply --repo factory-gitops
   ```

   Immediately trigger a deploy and confirm the bot's commit still lands. If it is
   rejected, disable and revisit bot signing:

   ```
   gh api -X DELETE repos/olafkfreund/factory-gitops/branches/main/protection/required_signatures
   ```

### Phase C — turn on the Fides change gate (SoD)

**Steps 5 and 6 are done.** The settings exist and the workflow runs; what
remains is step 7, and it is blocked on Factory#660 (four-eyes needs a second
human), not on plumbing.

Two things worth keeping when you return to this:

- `FIDES_SERVER_URL` must be the **public hostname**. A GitHub-hosted runner
  cannot resolve `fides-server.fides.svc.cluster.local`.
- `fides change-gate --trail` wants the **trail UUID that `trail start`
  returns**, not the `--trail` name you passed it. The name gets
  `400 invalid trail id`, and a 400 is not a verdict.

5. Per repo, create a Fides Flow and set the repo secrets/vars the workflow reads:
   `FIDES_SERVER_URL`, `FIDES_CI_KEY` (a Writer service-account key), and the
   `FIDES_FLOW_ID` variable. Optionally set `SN_CHANGE_NUMBER` for ServiceNow
   write-back.
6. Add `.github/workflows/fides-change-gate.yml` and let it run on PRs. Initially
   leave it **non-required** and observe: it starts a trail per PR and the gate
   HOLDs until a second human runs

   ```
   fides approve --trail <PR head sha> --role approver --reason "reviewed PR #<n>"
   ```

7. Once the approve flow is understood by reviewers, make the `change-gate` check
   **required** on `main` (add its context to the repo's required checks). Now no
   PR merges without both the GitHub review AND the recorded SoD approval.

## SoD identity model

The gate proves three roles are distinct people (`compliant: true` only when all
three are pairwise-distinct):

- **committer** — captured from the trail (the PR head commit author),
- **approver** — the second human who runs `fides approve --role approver`,
- **deployer** — whoever triggers the deploy (`--role deployer`, or the merger).

A reviewer approving their own PR fails the check. Fides advises; where ServiceNow
is wired, `fides servicenow change-check` writes the verdict + risk score onto the
Change Request, and ServiceNow's CAB remains the system of record.

## Control mapping

This is the mapping the two controls are *intended* to satisfy. The Status column
is load-bearing: a control matrix that lists a designed control the same way it
lists an operating one is how an audit gets told a gate is running when nothing
runs. Nothing below is claimed as operating until its phase above is done.

| Control | Requirement | How this satisfies it | Status |
|---|---|---|---|
| **SOX ITGC** (change management) | Changes authorized and approved by someone other than the developer; authorship attributable | SoD gate enforces committer != approver; signed commits make authorship non-repudiable. | Signing: designed, not enabled (Phase A). SoD: **not implemented** (Phase C, blocked). |
| **PCI-DSS 6.5** (change control) / 6.4 | Separation of duties between dev and deploy; documented approval before production change | Three-role SoD attestation (committer/approver/deployer distinct); the change gate is the documented, evidence-backed approval. | **Not implemented** (Phase C, blocked). |
| **NIST 800-53 AC-5** (Separation of Duties) | Divide mission functions so no single individual controls a whole critical process | Distinct commit / approve / deploy identities, enforced in CI, not by convention. | **Not implemented** (Phase C, blocked). |
| **NIST 800-53 CM-3 / CM-5** (change control, access restrictions for change) | Approve changes before implementation; restrict who can change | Required change-gate check + PR review gate the merge; branch protection restricts direct pushes. | Partial: PR review + branch protection **operating** today; the change-gate half **not implemented**. |

Signed commits additionally support **SLSA** provenance (verifiable source
identity) and the tamper-evidence expectations in SOC 2 CC8.1 / ISO 27001 A.8.32
(change management), complementing the Fides attestation chain recorded per trail.
