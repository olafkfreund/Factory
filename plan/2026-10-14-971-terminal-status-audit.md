---
status: draft
issue: 971
spec: spec/2026-10-14-971-terminal-status-audit.md
---

# Plan: terminal-status audit

## Approved decisions (from the spec)

- **Read-only audit** of AIFactory, PFactory, TFactory and CFactory at
  `origin/dev`. No code, deploy or data changes. Never run
  `fix-stuck-tasks.py`.
- **The split:**
  - Codex audits AIFactory;
  - agy audits TFactory;
  - the session audits PFactory and CFactory, and verifies every coder
    finding.
- **The method, per service:**
  1. Map the readers and the stores they read.
  2. Enumerate terminal writes: literals, helpers, reapers, handlers,
     timeouts, cancellation.
  3. Answer Q1–Q4 for each write.
  4. Trace `fix-stuck-tasks.py` (AIFactory, PFactory, TFactory).
- **The questions:**
  - **Q1, reachability:** would the write still land in the store the reader
    reads if the outcome happened at the earliest possible moment, before any
    artifact exists?
  - **Q2, symmetry:** does the opposite outcome on the same path also write a
    terminal state, to the same store?
  - **Q3, loudness:** if the write fails, is it logged at error level or
    raised, or swallowed?
  - **Q4, wiring:** is the write on a path the failing case actually calls,
    and is there a test proving the hook is invoked?
- **Worksheet row:**
  `service | file:line | outcome | store written | readers | Q1 | Q2 | Q3 | Q4 | verdict`.
  The verdict is `ok`, `instance` or `needs-check`.
- **What counts as an instance:** a concrete scenario, *outcome X at moment Y
  leaves the reader showing Z*, citing the write and the reader by
  `file:line`.
- **Issues:**
  - one per root cause, in the owning repo, siblings grouped;
  - title: `Terminal status lost: <what> stays <state> when <outcome>`;
  - body: the scenario, the write and reader, Q1–Q4, the wiring-test
    mutation, and a link to Factory#971;
  - dedup first, against the repo's open and closed issues and the known
    fixed ones: AIFactory#1430 and #1431, TFactory#1161, CFactory#431.
- **Verification:** the session re-reads every `instance`, plus at least 3
  `ok` rows per service. Rejected findings are recorded with a reason.
- **Findings file:** `docs/audits/2026-10-14-terminal-status.md` in Factory,
  shipped in this branch's docs PR. Merging it once green is pre-approved.
- **No structural guard** is built in this task.

## Steps

1. **Start the coder audits in parallel**, each in a read-only checkout
   (a detached worktree of `origin/dev`):
   - Codex in `AIFactory-971`;
   - agy in `TFactory-971`.

   The prompt carries the method, the four questions, the worksheet format
   and the instance rule above. It also says: read-only, no edits, no issues,
   no commands that change state; return the worksheet and the
   `fix-stuck-tasks.py` trace as text.
   - Verify: the exit status is OK, `denied_actions` is empty, the response
     is non-empty, and `git status` in the checkout is clean.
   - Trap: check that a coder process has finished by its real command line
     (`codex -p implement exec …`), not the wrapper name. That mistake in
     #1003 let Codex keep running.
2. **The session audits PFactory and CFactory** the same way, in detached
   worktrees `PFactory-971` and `CFactory-971`.
   - Verify: one worksheet per service, and every reader from step 1 of the
     method appears in at least one row's readers column.
3. **Verify the coder findings.**
   - For every Codex and agy `instance` row, and at least 3 `ok` rows per
     service, open the cited write and reader and confirm the scenario.
   - Mark the verdict `verified` or `rejected: <why>`.
   - Verify: no `instance` is left unverified.
4. **Dedup, then file issues** for verified instances.
   - Search with
     `gh search issues --repo olafkfreund/<R> "<file or symptom>"`, then
     `gh issue create -R olafkfreund/<R>` with the format above.
   - Verify: every verified instance row carries an issue link, or a link to
     an existing issue.
5. **Write the findings file** `docs/audits/2026-10-14-terminal-status.md`.
   It holds:
   - a per-service summary (counts of writes, instances and rejected);
   - the four worksheets;
   - the `fix-stuck-tasks.py` trace, mapping each repair to an instance, a
     known fixed issue, or a reason;
   - the issue links.

   Commit it on this branch, open the docs PR (intent, spec, plan and
   findings) and merge it once green.
   - Verify: the PR shows MERGED.
6. **Comment on #971** with the counts and links. Leave #971 open if
   instances were filed, since they are its children; close it if none were.
   Remove the four worktrees.

## Tests

None: no code changes. Correctness rests on the step 3 verification and the
`file:line` citations in every row.

## Rollback

Revert the docs PR. Filed issues can be closed as `not planned`, with a
reason.
