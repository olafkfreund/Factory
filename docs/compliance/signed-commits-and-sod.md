# Signed commits and segregation of duties

> Factory#316 (gap under the #310 compliance program)

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
- `.github/workflows/fides-change-gate.yml` — records each PR as a Fides change
  (trail) and runs `fides change-gate`, which HOLDs (fails the required check)
  until a second human records the SoD approval.
- This document — the rollout plan and the control mapping.

Nothing here changes live repo settings. Enabling signing and the gate is a
deliberate, per-repo `--apply` / required-check decision made after the
pre-flight below.

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

| Control | Requirement | How this satisfies it |
|---|---|---|
| **SOX ITGC** (change management) | Changes authorized and approved by someone other than the developer; authorship attributable | SoD gate enforces committer != approver; signed commits make authorship non-repudiable. |
| **PCI-DSS 6.5** (change control) / 6.4 | Separation of duties between dev and deploy; documented approval before production change | Three-role SoD attestation (committer/approver/deployer distinct); the change gate is the documented, evidence-backed approval. |
| **NIST 800-53 AC-5** (Separation of Duties) | Divide mission functions so no single individual controls a whole critical process | Distinct commit / approve / deploy identities, enforced in CI, not by convention. |
| **NIST 800-53 CM-3 / CM-5** (change control, access restrictions for change) | Approve changes before implementation; restrict who can change | Required change-gate check + PR review gate the merge; branch protection restricts direct pushes. |

Signed commits additionally support **SLSA** provenance (verifiable source
identity) and the tamper-evidence expectations in SOC 2 CC8.1 / ISO 27001 A.8.32
(change management), complementing the Fides attestation chain recorded per trail.
