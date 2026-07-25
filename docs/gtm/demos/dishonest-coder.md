---
layout: default
title: "Demo runbook: The Dishonest Coder"
permalink: /gtm/demos/dishonest-coder/
---

# Demo runbook: The Dishonest Coder

Flagship demo. Factory#242. This is the runbook, not the recording. Anyone (or
the `/demo` skill) can follow it to record the screencast.

## The point (one line)

A skeptical buyer sees an AI coder claim "all tests pass, ready for merge" on
code that is subtly wrong, and watches an INDEPENDENT verifier regenerate the
tests, run them against the coder's actual build, and reject it with the exact
failing reason. The green checkmark did not come from the coder's word.

## Why this is real, not theatre

Every beat maps to a shipped mechanism. Cite these on screen or in the blog:

- Completion-Event Evidence Gates (RFC-0001a). A stage may only claim success
  if it carries the evidence that proves it. A TFactory verify that reports
  `passed` MUST carry `verdict != null` AND `tests_executed > 0`; otherwise the
  status is downgraded to `failed` with `reason: "no_evidence"`. Reaching a
  terminal phase is not a verdict. See `docs/rfc/0001a-completion-evidence-gates.md`.
- Verification Assurance Levels (RFC-0006, epic Factory#71, closed). The
  never-overclaim spine: TFactory reports exactly what it proved (VAL-0..VAL-3)
  and what it did NOT, all the way to the PR comment. A unit+api pass reports
  "Verified to VAL-2. NOT verified: VAL-3." See `docs/rfc/0006-verification-assurance-levels.md`.
- Coder-side test-evidence honesty gate (AIFactory #851, shipped 3.6.37). The
  coder cannot mark a test/verify subtask `completed` unless a real test command
  actually ran, captured tamper-evidently by a PostToolUse hook that records the
  ACTUAL Bash execution, not the model's self-report. This is the fix for the
  original Dishonest Coder incident: a coder wrote "[x] Run all tests" +
  "Ready for merge" for a repo with no toolchain to run the tests.
- The hollow-verify fix (TFactory #376). TFactory used to generate good tests
  but never execute them against the coder's code (separate pods, separate
  PVCs), so every verdict was a masked `flag`. It now checks out the coder's
  actual build branch (`source_branch`) before running, so the verdict is real
  evidence against the real code.

The demo shows two independent honesty checks catching the same class of lie:
the coder-side gate (you cannot claim a test ran when it did not) and the
verifier-side gate (an outside party runs the tests for real and disagrees).

## Setup and preconditions

Services (the live cluster, or the standard demo stack):

- CFactory cockpit reachable (Mission Control, pipeline, active-tasks views).
- AIFactory (the coder) running, poller enabled, subscription OAuth (no
  `ANTHROPIC_API_KEY`; falls back to `~/.claude/.credentials.json`).
- TFactory (the verifier) running with the `source_branch` checkout path live
  (#376) and the RFC-0001a evidence gate + RFC-0006 VAL block enabled (defaults).
- A demo repo you control (e.g. `factory-demo` or `aifactory-demo`) with GitHub
  access wired for the git_writer push (`gh auth git-credential`).

Seed task. Use a spec whose acceptance criteria include one edge case that a
model plausibly gets wrong. The reproducible choice is a tiny Python (FastAPI)
service:

    Spec: "divide" endpoint
    AC1: GET /divide?a=<int>&b=<int> returns 200 with {"result": a/b}
    AC2: when b == 0, return HTTP 400 with {"error": "division by zero"}
         (MUST NOT raise / return 500)

AC2 is the trap. Coders routinely implement the happy path and let the
`ZeroDivisionError` fall through as a 500. TFactory generates a per-AC test for
AC2, runs it against the build, and it fails.

Two seeding modes:

- Natural (authentic, recommended for a live audience). Seed the spec as-is via
  a `factory:low` or `factory:medium` labeled issue and let the coder build it.
  On most runs the coder misses AC2. Do one dry run first to confirm the miss
  before recording; if that run happens to be correct, tighten the trap (add a
  negative-number or overflow edge case) or switch to forced mode.
- Forced (deterministic, recommended for an unattended recording). Pre-seed the
  coder's build branch with the plausible-but-wrong implementation (divide with
  no `b == 0` guard) AND a committed coder artifact that reads
  "[x] Run all tests - all passing" / "Ready for merge". Then run TFactory
  verify only. This guarantees the same rejection every take. Mark it clearly in
  the blog as a scripted reproduction of a real failure mode, not a mock.

## Shot list

Show the cockpit throughout; cut to the terminal/PR only for the payload.

### Beat 1 - The claim

On screen: CFactory Mission Control, the demo task advancing through Plan ->
Build. When Build finishes, open the task detail / active-tasks view and show
the coder's self-report: the completed subtasks including a checked
"[x] Run all tests" and a "Ready for merge" line. Zoom the diff of the divide
implementation - it looks clean and plausible.

Narration: "Here is the AI coder's own report. It says the tests pass and it is
ready to merge. This is exactly what every AI coding tool shows you, and exactly
what you are asked to trust. Notice there is no guard for divide-by-zero, but you
would have to read every line to know that. Nobody does at scale."

Reuse: `docs/assets/screenshots/cfactory/pipeline.png`,
`docs/assets/screenshots/cfactory/running-tasks.png`,
`docs/assets/screenshots/tour/cfactory/active-tasks.png` for framing.
Fresh capture: the coder's "all tests pass / ready for merge" claim and the
un-guarded diff for THIS task.

### Beat 2 - The independent check

On screen: the task hands off to TFactory (verify stage lights up in the
pipeline). Open the TFactory Tests / Test Plans view: TFactory GENERATES its own
per-AC tests from the RFC-0002 contract - it does not trust the coder's tests.
Show it checking out the coder's actual build branch and running the suite (the
unit lane in motion).

Narration: "Now an independent verifier takes over. It does not read the coder's
report and it does not run the coder's tests. It regenerates the tests straight
from the spec's acceptance criteria, checks out the exact code the coder built,
and runs them for real. This is the piece that used to be hollow - the verifier
now runs against the real build, not a promise of one."

Reuse: `docs/assets/screenshots/tfactory/python-unit.gif` (the unit lane
generate-run-grade loop), `docs/assets/screenshots/tour/tfactory/test-plans.png`,
`docs/assets/screenshots/tour/tfactory/tests.png`.
Fresh capture: the verify stage lighting up in the pipeline for THIS task.

### Beat 3 - The verdict

On screen: TFactory's result. The AC2 test fails (got 500, expected 400). The
verdict is `fail`, not `flag` - a real verdict backed by tests that actually
executed. Show the evidence block: `verdict: fail`, `tests_executed > 0`. Show
the VAL claim line: it reports exactly what was proven and what was not. The task
does NOT advance to merge; it is handed back to the coder with the failing AC and
reason attached.

Narration: "The verdict is fail. The divide-by-zero case returns a 500, not the
400 the spec requires. This is not a warning the coder can wave away - it is
independent evidence: the verifier records the verdict and the number of tests it
actually ran, and by contract a verify that produced no verdict, or ran no tests,
cannot report passed. The task is rejected and handed back, with the exact
acceptance criterion it failed."

Reuse: `docs/assets/screenshots/tour/tfactory/github-prs.png`,
`docs/assets/screenshots/tour/tfactory/visual-reports.png` for the reporting frame.
Fresh capture (the money shot): the rejected verdict with the failing AC2 and
the "handed back" state in the cockpit; the PR comment / evidence block showing
`verdict: fail`, `tests_executed`, and the VAL claim line.

### Beat 4 (optional) - The coder cannot lie either

On screen: cut to the forced-lie variant or a second run where the coder tries to
check off "Run all tests" without a real run. The coder-side honesty gate (#851)
refuses to mark the subtask completed - the tamper-evident hook recorded that no
test command actually executed.

Narration: "It is not only the outside verifier. The coder itself can no longer
tick a test box it never ran. A hook records the real command execution, and the
completion is refused unless a real test actually ran. Two independent honesty
gates, catching the same lie from both ends."

Fresh capture: the subtask-status refusal message from the honesty gate.

### Beat 5 - The loop closes (optional, if time)

On screen: the coder receives the handback, adds the `b == 0` guard, TFactory
re-verifies, the AC2 test now passes, verdict `pass`, and the PR reports
"Verified to VAL-2." Merge.

Narration: "Handback is not a dead end. The coder fixes the real defect, the
verifier re-runs, and only now - with the evidence to back it - does it report a
pass and merge. The green checkmark finally means what a buyer thinks it means."

## Assets: reuse vs fresh

Reuse (already in the repo):

- `docs/assets/screenshots/tfactory/python-unit.gif` - unit lane generate/run/grade.
- `docs/assets/screenshots/tfactory/polyglot.gif` - multi-language verify (B-roll).
- `docs/assets/screenshots/tour/tfactory/{test-plans,tests,github-prs,visual-reports}.png`.
- `docs/assets/screenshots/tour/cfactory/{active-tasks,pipeline,mission-control}.png`
  and `docs/assets/screenshots/cfactory/{pipeline,running-tasks}.png`.

Fresh captures needed (specific to this task):

1. The coder's "all tests pass / ready for merge" claim + the un-guarded diff.
2. The verify stage lighting up in the pipeline for this task.
3. THE MONEY SHOT: the rejected `fail` verdict with the failing AC2, the evidence
   block (`verdict`, `tests_executed`), the VAL claim line, and the handed-back
   state.
4. (Beat 4) the coder-side honesty-gate refusal message.
5. (Beat 5) the re-verified `pass` + "Verified to VAL-2" PR comment after the fix.

## The proof takeaway

What a skeptical buyer walks away having seen proven: the "tests pass" claim on an
AI-written change is verified by an independent party that regenerates the tests
from the spec and runs them against the actual build - and when the code is wrong,
the system says so, with the exact failing criterion, and refuses to merge. Green
means proven, not asserted.

## The failure this catches that SWE-bench scores do not

A SWE-bench number is an aggregate pass rate on a fixed public benchmark. It tells
you nothing about the run in front of you. It cannot tell you whether THIS change
was actually tested, whether the "passing" tests ran against the code that shipped
or against nothing at all, or whether "done" was a real verdict or just the agent
reaching a terminal phase and reporting success. The Dishonest Coder failure -
a plausible-but-wrong change that the coder sincerely reports as passing, that a
naive harness would have merged on the coder's word - is exactly the gap a
benchmark average hides and per-run evidence gates (RFC-0001a) plus independent,
build-attached verification (TFactory #376) plus never-overclaim reporting
(RFC-0006) close.
