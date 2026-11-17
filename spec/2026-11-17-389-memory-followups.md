---
status: approved
issue: 389
intent: intent/2026-11-17-389-memory-followups.md
---

# Spec: RFC-0021 memory follow-ups

One PR per service repo (AIFactory, PFactory, TFactory; base `dev`). The
`memory/` tree stays vendored: same behaviour in all three, formatting per repo.

## Design

### (b) Cross-process lock (#3796)

New `memory/locking.py`: `locked(memory_dir, wait=2.0)` is a context manager that
takes `fcntl.flock(LOCK_EX | LOCK_NB)` on the sidecar `<memory_dir>/.memory.lock`,
retrying every 20 ms until `wait` seconds pass, then raises `LockTimeoutError`
(a subclass of `OSError`). It is re-entrant per thread (a thread-local set of
held directories), because `flock` on a second descriptor in the same process
would otherwise deadlock `promote` -> `confirm`. Where `fcntl` is missing (not a
supported pod platform) it does nothing.

Fail toward not writing: every caller already catches `OSError`
(`scratchpad.observe`, `record_dead_end`, `retention.confirm`) or `Exception`
(`gates.promote`, the `record_gotcha` tool); `LockTimeoutError` therefore skips the
write and logs. Locked sections: `scratchpad.observe`, `record_dead_end`,
`retention.confirm`, `gates.promote` (whole run), `patterns.append_gotcha` /
`append_pattern`, the `record_gotcha` tool (read, repeat check, append), and the
pool merge. One lock per memory directory, not per file: the sections are short
and promote touches all three files.

### (c) Graphiti write path (#3797)

No new Graphiti capability. Graphiti is written from four places: the primary
path in `agents/memory_manager.save_session_memory` (`save_structured_insights`
or `save_session_insights`), `graphiti_helpers.save_to_graphiti_async`, and
`patterns.append_gotcha` / `append_pattern`. One helper,
`graphiti_helpers.gate_for_graphiti(payload, session_type=None)`, returns a deep
copy with the file path's rules applied, and each of the four calls it before
the existing Graphiti call:

- cap: one shared budget `CAPS[session_type]` over the list fields
  `what_worked`, `what_failed`, `recommendations_for_next_session` and, in
  `discoveries`, `patterns_found`, `gotchas_encountered`, `patterns_discovered`,
  `gotchas_discovered`, `recommendations`, `file_insights`, `files_understood`
  (same order and shared-budget rule as `sessions._apply_cap`). Idempotent, so
  the already-capped session path is unchanged.
- trust: gotcha items (`gotchas_encountered`, `gotchas_discovered`) get
  `trust.UNVERIFIED` appended while `trust.tainted()`, once.

`append_gotcha` also appends the marker to the file bullet while tainted, and
counts writes per memory directory per process against `CAPS[session_type]`
(the same scope as the `record_gotcha` tool counter: one process, one session).
`append_gotcha` / `append_pattern` catch `OSError` around the locked section and
log, so `LockTimeoutError` never reaches a caller.

### (a) Project pool for PFactory and TFactory (#3795)

New `memory/pool.py` in PF/TF: `pool_dir(project_dir)` is
`project_dir/.pfactory/memory`, and `pool_dir_from_spec(source_spec_dir)` is
`source_spec_dir.parent.parent / "memory"` (the same directory when the spec
lives under the project; this is how AIFactory anchors it, because `project_dir`
may be a worktree or a job clone) (`.tfactory/memory` in TFactory), derived from the
project directory argument and nothing else (no env var, no global path, no
listing of siblings). `seed(project_dir, spec_dir)` copies the pool into a fresh
spec `memory/` at setup (after `copy_spec_to_worktree`, which replaces the spec
directory); `sync(spec_dir, project_dir)` merges the spec memory into the pool at
the end of `save_session_memory`. Both never raise. Dead-end recall then works
through the existing `scratchpad.dead_end_context` because the pooled
`scratchpad.json` is in the spec memory.

### Pool merge (all three; closes the stale-snapshot gap)

`pool.merge_into(src, dst)` under `locked(dst)`: `scratchpad.json` entries keyed
by kind and key, the higher `n` wins, ties go to the later `last`, `promoted`
and `body` are kept if either side has them; `bad` and `ab` take the larger value of the two sides, so a trust mark
or abandonment seen by either snapshot survives; `confirmed.json` keeps the later
stamp per key; `gotchas.md` appends entries whose stripped body is missing in
dst; other files are copied only if absent in dst or newer in src. AIFactory's
`sync_memory_to_project` and `sync_memory_to_source` call it instead of
`copytree` (the latter was an unlocked overwrite of newer counts). The seed-in
copy is unchanged: it fills a fresh worktree whose own files win afterwards.

### Measures

A fixture test per repo records, as in RFC 6.2: memory bytes after 1/5/20
sessions with and without the pool, tokens of recalled dead ends (chars/4), and
Graphiti items sent versus file items kept. The numbers go into RFC 6.2.

## Alternatives rejected

- One lock per file: promote needs three and ordering them invites deadlock.
- `portalocker` or similar: new dependency, no gain on Linux pods.
- A shared pool service: new infrastructure; the pool is a directory.
- A pool path from an environment variable: could point two projects at one
  directory; the owner decision is project scope.
- Extending Graphiti to record dead ends: ruled out by the owner.
- Blocking indefinitely on the lock: a stuck process would stall a build.

## Risks

- Lock sidecar `.memory.lock` is copied into pools and specs: zero bytes,
  harmless. It is not a lock held across copies (the copy has its own).
- NFS and similar: `flock` may not exclude across hosts. The pool lives on the
  co-mounted volume; documented limit, the wait still bounds the damage.
- PF/TF anchor the pool on `source_spec_dir` (durable volume) for the sync and on
  the real `project_dir` for the seed, the AIFactory lesson from #1030. A run
  without `source_spec_dir` does not sync (limit, not solved here).
- Merge keeps the higher count, so a deliberate reset in a spec does not clear
  the pool; resets are not a feature.

## Verification

Per repo, new tests (mutation check = the gate removed turns the test red):

- two real processes (`multiprocessing`) each add 40 observations / confirmations
  to one directory: with the lock the total is 80; with `locked` made a no-op the
  mutation test shows lost updates; a held lock makes a third writer time out and
  not write.
- Graphiti: a fake `GraphitiMemory` receives at most the cap and the unverified
  marker while tainted; with the gate bypassed the test fails.
- PF/TF: `pool_dir` equals `project_dir/.<brand>/memory` for two project dirs and
  never the other's; a dead end recorded twice in project A spec 1 is recalled in
  A spec 2 and not in project B; seed with a different project's pool is absent.
- Merge: a stale snapshot does not lower a count or drop a gotcha.
- `ruff`, repo test suite for `tests/test_memory_*.py`.
