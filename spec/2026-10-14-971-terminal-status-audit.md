---
status: draft
issue: 971
intent: intent/2026-10-14-971-terminal-status-audit.md
---

# Spec: terminal-status audit

Approved split: Codex audits AIFactory, agy audits TFactory, and the session
audits PFactory and CFactory and checks every finding. No structural guard
is built in this task. The docs PR may merge once green.

## Design

### Method (identical per service, so findings compare)

1. **Map the readers first.** List every place status is *reported*:
   - status or progress API endpoints;
   - cockpit and UI data sources;
   - MCP `task_status` and `get_build_progress`;
   - CLI and runbook queries.

   Each reader reads one or more **stores**, such as a `status.json`, a DB
   row, a plan file, an event stream, or `lane_progress`. Starting from the
   readers matters: a write is only correct if it lands in the store the
   reader actually reads.
2. **Enumerate terminal writes.** Find every code path that moves a task,
   build, lane or stage into a terminal state, including:
   - failed, error, complete, done, succeeded, cancelled, timed out and
     human review;
   - writer helpers (`update_status`, `set_phase`, `write_status`,
     `_fail`, `_done`, `on_done`/`on_fail`, reapers, exception handlers,
     timeouts and cancellation);
   - literal assignments.

   A regex is the starting point only: about 12 to 25 literal writes per
   service. Helpers and enums need reading.
3. **Ask four questions of each write:**
   - **Q1, reachability.** If this outcome happened at the earliest possible
     moment (before any artifact exists), would the write still land in the
     store the reader reads?
   - **Q2, symmetry.** Does the opposite outcome on the same path also write
     a terminal state, to the same store?
   - **Q3, loudness.** If the write fails, is it logged at error level or
     raised, or swallowed and returned silently?
   - **Q4, wiring.** Is the write on a path the failing case actually calls?
     Is there a test proving the hook is invoked, not only that the helper
     works?
4. **Read each `fix-stuck-tasks.py`** (AIFactory, PFactory and TFactory, about
   270 lines each, forked). Each stuck state a script repairs is a symptom.
   Trace it back to the write that should have prevented it.

### Output

- **One worksheet row per write:**
  `service | file:line | outcome | store written | readers of that store | Q1 | Q2 | Q3 | Q4 | verdict`.
  The verdict is `ok`, `instance` or `needs-check`.
- **An instance requires a concrete scenario:** *outcome X at moment Y
  leaves the reader showing Z*. It must cite the write and the reader by
  `file:line`.
- **Each verified instance gets one issue** in the owning repo. The issue
  carries:
  - the title `Terminal status lost: <what> stays <state> when <outcome>`;
  - the scenario;
  - the write and the reader;
  - the four answers;
  - the wiring test that would catch it, stated as a mutation ("remove the
    call and this test must fail");
  - a link to #971.
- **Findings file:** `docs/audits/2026-10-14-terminal-status.md` in Factory.
  It contains the per-service summary, the worksheet, the issue links and
  the `fix-stuck-tasks.py` trace. That trace notes whether each script's
  repairs map to a filed instance or to a known, fixed one.

### Verification of coder findings

Codex and agy return their worksheets as text, with no edits and no issues.
The session re-reads the write and the reader at the cited lines for every
`instance`, and for a sample of `ok` rows (at least 3 per service). Only
verified instances are filed. A finding that fails verification is recorded
in the findings file as `rejected: <why>`, so the next audit doesn't redo it.

### Dedup

Before filing, search the owning repo's issues for the file and symptom.
Known fixed instances (AIFactory #1430 and #1431, TFactory #1161, CFactory
#431) are listed as `known, fixed`, unless the audit shows the fix doesn't
cover a sibling path.

## Alternatives rejected

- **Fixing instances inside this task.** Each fix needs its own design and
  wiring test, and bundling them makes review impossible. The intent rules it
  out.
- **A grep-only sweep.** It misses helper-mediated and enum writes, which is
  where three of the four known instances were.
- **One auditor for all four services.** It's slower, and the split was
  approved. The identical method and worksheet keep the results comparable.

## Risks

- **False positives** from coder auditors filing noise. Mitigated by session
  verification before anything is filed, and by the concrete-scenario rule.
- **False negatives** from a write missed in step 2. Mitigated by starting
  from readers and the stuck-task scripts, which reach the write from the
  symptom side.
- **Issue spam.** Siblings are grouped: one issue per root cause, listing
  every affected `file:line`.

## Verification

- Every service has a worksheet. Every `instance` row links an issue or
  says `rejected: <why>`.
- Every `fix-stuck-tasks.py` repair maps to an instance, a known fixed issue,
  or a stated reason.
- The findings file is merged in Factory, and #971 gets a comment with the
  counts and links.
