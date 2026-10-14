---
status: draft
issue: 971
author: olafkfreund
---

# Intent: find every terminal status that can fail to reach its reader

## Problem

Four defects in one week shared one shape: AIFactory#1430 (twice),
TFactory#1161 and CFactory#431. A component reaches a terminal state and
records it in one place, while whatever reports status reads from another.
Nothing errors, and the status never moves.

Two properties make this class expensive:

- **It fails towards "running".** A dropped terminal write leaves the last
  non-terminal value in place. `failed` gets attention; `in_progress` gets
  waited on. The earliest failures are the most likely to be lost, because
  they never wrote the artifact the status lives in.
- **A succeeded task stuck at "running" blocks the sequence.** The card never
  advances, even though the work is done and pushed.

`apps/backend/scripts/fix-stuck-tasks.py` exists, forked, in PFactory,
AIFactory and TFactory. That is evidence the class has been around for a long
time.

Instances have been fixed one at a time. Nobody has asked the issue's question
of every terminal-state write in the fleet: *if this outcome happened at the
earliest possible moment, would the status still land?*

## Proposed outcome

- A per-service audit of every terminal-state write, in AIFactory, PFactory,
  TFactory and CFactory. Each write gets:
  - where it is written and where it is read;
  - a yes or no answer to the issue's question;
  - whether a dropped write is loud or silent;
  - whether its success and failure paths are symmetric.
- **One GitHub issue per real instance**, in the owning repo, with the failing
  scenario and the wiring test that would catch it. Fixing them is follow-up
  work, not part of this task.
- A short findings document committed in Factory, linking the issues. It also
  records why each `fix-stuck-tasks.py` exists, meaning which stuck states it
  repairs, because each of those is a symptom pointing at an instance.

## Affected users and systems

- **Read-only:** the backends of AIFactory, PFactory, TFactory and CFactory,
  plus their reapers, completion hooks, status endpoints and cockpit or UI
  readers.
- **Writes:** one findings file in Factory, and new issues in the four repos.
  No code changes.

## Constraints

- Read-only on the services. No code, deploy or data changes, and no running
  of `fix-stuck-tasks.py`.
- An instance is filed only with a concrete scenario: *outcome X at moment Y
  leaves status Z*. "Looks asymmetric" alone is not enough.
- No duplicate issues. Check the already-fixed instances first: AIFactory
  #1430 and #1431, TFactory #1161, CFactory #431.
- Coder output is untrusted. Every finding Codex or agy reports gets checked
  against the code before an issue is filed.

## Open questions

1. **Who audits what?** I recommend one service each, run in parallel:
   - Codex: AIFactory, the biggest, with the reaper and k8s Jobs;
   - agy: TFactory;
   - me: PFactory and CFactory, plus checking every reported finding.
2. **Should a cheap structural guard come out of this task?** For example, a
   test helper making "the failure hook is wired" a required mutation, from
   point 4 of the issue. My recommendation is **no**: decide it from the
   findings, as a separate task.
3. **Merge approval in advance:** may I merge this task's docs PR once CI is
   green? There are no code PRs.
