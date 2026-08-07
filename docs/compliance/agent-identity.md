# Agent identity, and why "never merge" is not a control

Factory#611. Compliance domain 6 (change management and segregation of duties),
[Factory#310](https://github.com/olafkfreund/Factory/issues/310).

Agents in this fleet are routinely instructed "open PRs, never merge". This
document records what that instruction actually is today (an advisory), what
measurement backs that statement, why the two options the issue expected to be
available today are not, and precisely what the operator has to provision before
any of it changes.

Nothing here is aspirational. Every number below was read from the live GitHub
API on 2026-08-07 and can be re-read with the commands given.

## The constraint, and why it exists

"Never merge" is not bureaucratic. It keeps landing order under a single point
of control. The operator's worked example: four consumer repos had pinned the
head SHA of an open hub pull request; because Factory squash-merges, that SHA
died with the branch and all four needed re-pointing before they could merge. A
parallel agent cannot see that dependency. One sequencing point can.

So it is a constraint with real consequences when violated, and today it is
enforced by asking agents nicely.

## Measured state

**One account exists.**

```
$ gh api repos/olafkfreund/Factory/collaborators \
    --jq '.[] | .login + " " + .type + " admin=" + (.permissions.admin|tostring)'
olafkfreund User admin=true
```

Same single entry on AIFactory, PFactory, TFactory, CFactory and factory-gitops.
Every agent authenticates as that account. It is the root cause of everything
below, not a detail.

**No merge in the fleet is attributable.**

```
$ python3 scripts/check_merge_attribution.py --limit 100
600 merges: 0 attributable, 600 indistinguishable, 0 unknown.
```

Six repos, the last 100 merged pull requests each. Every one records
`mergedBy: olafkfreund`, which is equally consistent with the operator merging
and with an agent merging. The command is the mechanical form of the issue's
acceptance criterion 3, and it is the thing in this repo that will notice the day
the answer changes.

**Admins are exempt from branch protection, by design.**

```
$ gh api repos/olafkfreund/Factory/branches/main/protection \
    --jq '{enforce_admins:.enforce_admins.enabled, reviews:.required_pull_request_reviews}'
{"enforce_admins":false,"reviews":null}
```

Same on AIFactory main and factory-gitops main.
`scripts/apply_branch_protection.sh` declares `ENFORCE_ADMINS=0` for all six
repos and explains why: the gitops CD bot pushes directly to factory-gitops main,
and the factory's own auto-merge loop runs `gh pr merge` with an admin token.
Flipping it to true fleet-wide breaks both.

## Why the cheap options are not available

Factory#611's body lists branch-protection reviews and CODEOWNERS as "available
today". Measured against the state above, neither is.

### Requiring an approving review from a non-author account

GitHub does not let the author of a pull request approve it. Agents open pull
requests as `olafkfreund`, and `olafkfreund` is the only account with access.
So a review requirement produces no approver at all: every agent pull request
becomes unmergeable by anyone except an admin using the `enforce_admins: false`
bypass -- which is exactly the capability the agents hold.

The result is inverted. It blocks the honest path and leaves the path it was
added to close wide open. It would also have to be paired with
`enforce_admins: true` to bind an admin token at all, which breaks the CD bot and
the auto-merge loop as above.

This is not an argument against review requirements. It is an argument that they
require a second account first.

### CODEOWNERS on security-relevant paths

Not available either, and this one is worse than expected, because it is already
deployed and already doing nothing.

**PFactory, TFactory and AIFactory each carry a root `CODEOWNERS` file today.**
Each assigns every path -- `*`, `/.github/`, `/scripts/`, `/Dockerfile`,
`/SECURITY.md`, `/CODEOWNERS` itself -- to `@dataseeek`, a real GitHub user who
is not a collaborator on any of the three. GitHub ignores a CODEOWNERS rule whose
owner lacks write access, entirely. Its own validator says so:

```
$ gh api repos/olafkfreund/PFactory/codeowners/errors --jq '.errors | length'
8
$ gh api repos/olafkfreund/PFactory/codeowners/errors --jq '.errors[0].message'
Unknown owner on line 9: make sure @dataseeek exists and has write access ...
```

Three files, 24 rules, zero ownership assigned. Anyone opening those repos --
an assessor included -- reads a file that appears to give every security-relevant
path a named owner.

`scripts/apply_branch_protection.sh` compounds it from the other side. It carries
`CODE_OWNER=1` for exactly those three repos, but the flag is only read inside
the `required_pull_request_reviews` block, which is null wherever `REVIEWS=0` --
which is everywhere. So the declared intent points at a file that owns nothing,
through a setting that is never applied.

That gap is now measured rather than assumed: the same script checks CODEOWNERS
validity wherever it declares `CODE_OWNER=1`, and the nightly
`branch-protection drift` workflow is red on all three until somebody decides
what the file is for. The three available decisions -- grant `@dataseeek` write
access, repoint the rules at an account that has it, or delete the files -- are
all the operator's, which is why this reports rather than fixes.

None of that changes the conclusion above: even a perfectly valid CODEOWNERS
cannot require a review the sole account is not allowed to give.

### Accepting it as advisory

This is the honest description of the status quo, and this document is that
acceptance written down. What it costs is stated under "what stays broken".

## What the operator has to provision

**A GitHub App (or a distinct machine account) that agents authenticate as
instead of the operator.** This is the only option that changes anything, and it
cannot be done from a pull request -- it needs account-level and organisation-level
authority that no agent in this fleet has or should have.

Concretely:

1. Create a GitHub App under the `olafkfreund` account, installed on the six
   fleet repos. Repository permissions: Contents read/write, Pull requests
   read/write, Issues read/write, Actions read, Metadata read. Deliberately NOT
   granted: Administration (branch protection, repository settings) and
   Members.
2. Issue agents an installation token for that App, and stop giving them the
   operator's PAT. The App identity appears in `mergedBy` and in the audit log as
   `<app-name>[bot]`, distinct from `olafkfreund`.
3. Deny merge to the App. With Contents write but no bypass of branch protection,
   and `enforce_admins: true` once the App is no longer an admin, an agent's
   `gh pr merge` fails at the API rather than being asked not to try.
4. With a second identity in play, revisit the review requirement. It becomes
   satisfiable: the operator, as a non-author, can approve an App-authored pull
   request. That is the point at which CODEOWNERS on
   `apps/kyverno-policies/**` and the RBAC manifests starts doing work.

Steps 3 and 4 are what turn the instruction into a mechanism. Step 1 alone
already satisfies acceptance criteria 1 and 3, because a merge would then be
attributable even if it were still permitted.

The broader exposure is the reason to do this even if merging were solved another
way: agents currently hold the operator's FULL GitHub authority for every
operation -- branch deletion, protection changes, releases, repository settings,
package visibility. Merging is one symptom of a token that is scoped to a person
rather than to a job.

## What stays broken meanwhile

- Whether any given merge was performed by a human or by an agent cannot be
  determined, in either direction, by anyone. Not by an auditor, not by the
  operator six months later, not by the agent that performed it.
- The failure mode is not only missed violations. It manufactures plausible false
  ones: on 2026-08-07 an agent reasoning correctly over everything the platform
  exposes reconstructed a process failure that had not happened, and could not
  distinguish its reconstruction from a real breach. Settling it required the
  operator's testimony. A control whose output requires a person to interpret it
  is not a control.
- Every "agents must not X" constraint the program adds inherits the same
  property. This is not specifically about merging.
- Nothing detects a violation of the advisory. That is stated rather than dressed
  up: `scripts/check_merge_attribution.py` measures the ABSENCE of attribution.
  It cannot catch an agent merging, and no analysis of this metadata could,
  which is the whole finding.

## What is implemented in this repo

- `scripts/check_merge_attribution.py` -- the on-demand audit command above, with
  an offline `--self-test` that is observed failing when the control is removed
  (docs/dev/gate-honesty.md).
- `tests/test_merge_attribution.py` -- offline verdict tests, both directions.
- A CODEOWNERS-validity check in `scripts/apply_branch_protection.sh`, run
  wherever the intent table declares `CODE_OWNER=1`, with both directions covered
  offline in `tests/test_branch_protection_intent.py`. This one CAN go green from
  a pull request, and it is red today for a real reason.
- This document.

Deliberately not implemented: any change to branch protection, to the CODEOWNERS
files, or to repository settings. A review requirement is inert until the
identity exists (above), and what the CODEOWNERS files should say is a decision
about who reviews what. Both are the operator's.
