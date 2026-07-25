# Demo runbook: HITL governance approve/merge flow

Tracking: Factory#245. This runbook produces the screencast; recording is a
follow-up task. Plain text only, no emojis or icons.

## The point (one line)

The human stays in control: the factory can build autonomously, but nothing
merges to main without a person signing off, and the platform blocks any change
that tries to skip that sign-off.

## What this demo proves

Governed autonomy. The factory does the work; a human reviews it, sees the
cost, and either approves the merge or removes the run. The merge itself is
gated by branch protection and, where staged, the Fides change gate with
segregation-of-duties approval, so the sign-off is enforced by the platform, not
just by convention. Every action is captured for the audit trail. This is the
concrete answer to EU AI Act Article 14 human-oversight expectations for a
high-automation system: a named human can understand the output, intervene, and
stop it before it lands.

## Real capabilities this demo exercises

- CFactory cockpit HITL actions: Approve, Remove, and per-run cost visibility
  (tokens and, in metered billing modes, dollar cost). Reference: cockpit HITL
  action fixes, CFactory#130 and the accuracy fixes (token cost, Remove, stall
  clock).
- The PR endgame: on a green build the factory opens the pull request, requests
  Copilot review, and after human approval + merge it re-tests the merged
  result. Reference: the parr-run PR endgame (auto-PR -> review -> merge ->
  re-test).
- Change management / separation of duties: branch protection applied as code
  (Factory#316, scripts/apply_branch_protection.sh) requiring a pull request and
  review before anything lands on main; the CI-gated merge policy in
  docs/rfc/0009-ci-gated-auto-merge.md (all required checks green AND assurance
  floor AND required approvals satisfied); and the Fides change gate with
  four-eyes / segregation-of-duties approval, staged via the compliance program
  (Factory#310).

Honesty note for the presenter: branch protection and the CI-gated merge policy
are the enforced gate to demo live. The Fides change gate / four-eyes approval
is staged (see docs/compliance/branch-protection.md and the Factory#310
compliance program) - present it as the compliance layer coming online, not as
already enforced fleet-wide, unless it has been applied on the demo repo by
showtime. Do not claim more enforcement than is live on the day.

## Setup

Precondition: one completed, green build sitting in the cockpit awaiting human
approval. Do not start from a cold PARR run in this demo - the governance flow
is the story, not the build.

1. Have a finished run from an earlier PARR pass (any small green feature works).
   Its build is complete, verification is green in TFactory, and it is parked at
   the approval step - the PR is open but not merged.
2. Open the CFactory cockpit on the run's task-detail view. Confirm the run
   shows a green/complete state and the Approve, Remove, and cost fields are
   visible.
3. Have the target repo's main branch protection active so the "blocked without
   approval" shot is real: a pull request and review are required, direct push
   to main is refused. Confirm with the repo settings or a dry-run push before
   recording.
4. Sign in as the reviewer identity (a person, not the automation bot) so the
   approval and the merge are attributed to a human in the audit trail. If
   demonstrating segregation of duties, the reviewer must be a different
   identity from the one that produced the build.

## Shot list

1. The parked run. Cockpit task-detail: the completed green run, its title, the
   verdict from TFactory, and the token/cost readout. Establishes that the
   factory finished and is waiting on a human.
2. The reviewer inspecting the run. Scroll the run detail: the plan, the diff /
   PR link, the verification evidence, and the cost. Show that the reviewer can
   actually understand what will merge before deciding - this is the oversight
   moment.
3. The gate blocks an unapproved change. Before approving, show the merge being
   refused without sign-off: the open PR on GitHub with branch protection
   requiring a review (required checks + required approval), or an attempted
   direct push to main rejected. This is the "nothing merges without sign-off"
   proof - the platform enforces it.
4. The approve/merge action. Back in the cockpit, the reviewer clicks Approve.
   The PR endgame proceeds: Copilot review is present, the human approval
   satisfies the merge policy, and the PR merges. Capture the state change from
   "awaiting approval" to "merged".
5. (Optional, strong) The remove path. On a second parked run, show Remove -
   the human rejecting a run instead of approving it. Reinforces that approval
   is a real decision, not a rubber stamp.
6. Re-test after merge. Show the post-merge re-test kicking off against the
   merged main and coming back green. Closes the loop: the approved change is
   verified in its final merged form, not just as a branch.
7. The audit trail. Close on where the decision is recorded - who approved, when,
   at what cost - tying the human action to a durable record.

## Narration

"The factory just built and verified this change on its own. But it has not
merged. It is waiting - here, in the cockpit - for a person.

This is the reviewer's view. I can see the plan the factory followed, the diff
it is proposing, the verification evidence behind the green check, and exactly
what it cost to produce. Enough to actually decide, not just approve blind.

Watch what happens if we try to merge this without sign-off. Branch protection
on main refuses it: a review is required, the checks have to be green, and a
direct push is rejected. The rule is enforced by the platform - there is no path
around it.

Now I approve. The pull request has already been through review; my approval
satisfies the merge policy, and it merges. If instead I did not trust this run,
I would click Remove and it never lands.

And because the change changed when it merged, we re-test the merged main - not
the branch. Green. The change that shipped is the change that was verified.

Every step - who approved, when, at what cost - is on the record. That is
governed autonomy: the machine does the work, a named human stays in control,
and the audit trail proves it. That is exactly the human oversight the EU AI Act
asks for."

## Assets: existing vs fresh capture

Existing assets to reuse where they fit:

- docs/assets/screenshots/cfactory/mission-control.png, running-tasks.png,
  tokens.png - good for context/establishing shots of the cockpit and the cost
  readout.
- docs/assets/screenshots/portal-ui/cfactory-portal.png - cockpit portal
  overview.

Fresh capture required (these are the substance of the demo and must be current):

- The parked green run on the cockpit task-detail with Approve / Remove / cost
  visible (shots 1, 2).
- The GitHub PR showing branch protection blocking merge without approval, or a
  rejected direct push (shot 3). This is the load-bearing governance shot -
  capture it live, do not reuse a stale screenshot.
- The Approve click and the resulting merge state change (shot 4).
- The Remove action on a second run, if included (shot 5).
- The post-merge re-test going green (shot 6).
- The audit-trail record of the approval (shot 7).

Prefer a single screen recording over stills for shots 3-6 so the state
transitions are visible; pull stills from it for the blog post.

## Proof takeaway

Governed autonomy, demonstrated end to end: a human reviews the factory's
output with full cost and evidence in view, explicitly approves or removes it,
and the merge is enforced by branch protection and the CI-gated merge policy
(with the Fides change gate / four-eyes segregation-of-duties approval as the
staged compliance layer). The approval, the identity, the cost, and the merge
are all captured in the audit trail. This is the direct, showable answer to EU
AI Act Article 14 human oversight: a person can understand, intervene in, and
stop the system's output before it takes effect, and there is a durable record
that they did.
