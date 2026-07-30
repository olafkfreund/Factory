# Demo runbook: HITL governance approve/merge flow

Tracking: Factory#245. The approve/merge core of this runbook is recorded - see
"Recorded artifacts" below for the GIF and stills, and for the parts of the shot
list they do and do not cover. Plain text only, no emojis or icons.

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

Two open defects that bear directly on what this demo asserts. Check both before
presenting; if either is still open, say so rather than letting the screen imply
otherwise.

- Factory#460: the cockpit shows "Done." for an approve/merge that GitHub
  REFUSED, and the audit entry records it as ok/200. So "the banner said it
  merged" is not, today, evidence that it merged - confirm against the PR. Found
  while recording this runbook: the first attempt reported success on a merge that
  had been refused on a conflict.
- CFactory#251: the audit actor is the presented API key, not a person. Until that
  is fixed the trail proves an approval happened, not WHO approved. Do not read
  the "who approved" line of the narration off the Audit view as it stands.

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

## Recorded artifacts

Recorded 2026-07-30 against the live cluster, in one unedited take. The run was
real: AIFactory task `109-add-an-ordinal-n-helper` on the `aifactory-demo` repo
built to `human_review`, Approve was clicked in the cockpit, and the confirmed
action opened and merged `aifactory-demo` PR #465 (merge commit 53802e5 on main).
The cockpit-side software was on the fleet's current main at capture time
(AIFactory image sha-6df8bf5 = main HEAD 6df8bf5; CFactory sha-285a2e1 = main HEAD
285a2e1).

- docs/assets/demos/hitl-governance.gif - the whole approve/merge chain, 46s,
  2.9 MB. The state transitions are the point; use the stills for detail.
- docs/assets/demos/hitl-governance/01-needs-you-review-gate.png - the Needs-you
  inbox, "Review gates" filter: builds the factory finished and parked for a
  person.
- .../02-task-in-human-review.png - the card itself: Code stage `human_review`,
  2/2 subtasks done, Approve / Reject / Remove offered, Unstick correctly
  refused because the task is in review, not stuck.
- .../03-disclosed-endpoint-calls.png - the load-bearing shot. Approve only
  PROPOSES: the rationale plus the exact upstream writes it will make, as
  root-relative paths (`POST /api/tasks/.../worktree/create-pr` then `POST
  .../worktree/merge`), with Cancel and Confirm. Nothing has been written yet.
  The root-relative form is the SSRF guard in `actions.is_safe_endpoint` made
  visible.
- .../04-merged-card-done.png - after Confirm: Code stage `done`, STAGE COMPLETE,
  and Approve / Reject now refused because the task is no longer in review.
- .../05-audit-entry.png - the audit trail: `approve_review` against
  `aifactory/api/tasks/...`, result `ok 200`. The ACTOR column is deliberately
  covered in this capture - CFactory records the presented API key verbatim as the
  actor, which is a live credential and must not appear in a committed frame
  (CFactory#251). The same issue is why this shot does NOT yet prove "a named
  human approved it".
- .../06-merged-pull-request.png - the write itself, on GitHub: PR #465 merged
  into main, two AIFactory commits.

Not covered by this recording - do not present these as captured:

- Branch protection refusing an unapproved merge (runbook shot 3). The demo repo
  has no branch protection precisely so the throwaway merges are harmless, so the
  blocked-merge shot has to be taken on a protected repo.
- The Remove path (shot 5) and the post-merge re-test going green (shot 6).

Existing assets that still fit as establishing shots are listed above.

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
